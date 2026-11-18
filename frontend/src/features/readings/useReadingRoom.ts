import { useQuery, useQueryClient } from "@tanstack/react-query";
import type { Dispatch, SetStateAction } from "react";
import { useCallback } from "react";
import { useListBooks } from "../../api/generated/books/books";
import type {
  BookResponse,
  ReadingResponse,
  VocabularyResponse,
} from "../../api/generated/models";
import {
  getListReadingsQueryKey,
  useListReadings,
} from "../../api/generated/readings/readings";
import {
  bootstrapOwner,
  useGetSystem,
} from "../../api/generated/system/system";
import { useListVocabulary } from "../../api/generated/vocabulary/vocabulary";
const emptyBooks: BookResponse[] = [];
const emptyReadings: ReadingResponse[] = [];
const emptyVocabulary: VocabularyResponse[] = [];
export function useReadingRoom(bookId: string) {
  const client = useQueryClient();
  const owner = useQuery({
    queryKey: ["owner-bootstrap"],
    queryFn: () => bootstrapOwner(),
    staleTime: Infinity,
    retry: false,
  });
  const books = useListBooks({ query: { enabled: owner.isSuccess } });
  const vocabulary = useListVocabulary(undefined, {
    query: { enabled: owner.isSuccess },
  });
  const system = useGetSystem({
    query: { enabled: owner.isSuccess, retry: false },
  });
  const readings = useListReadings(bookId, {
    query: { enabled: owner.isSuccess && !!bookId, refetchInterval: 4000 },
  });
  const setReadings: Dispatch<SetStateAction<ReadingResponse[]>> = useCallback(
    (update) => {
      client.setQueryData<ReadingResponse[]>(
        getListReadingsQueryKey(bookId),
        (old) => (typeof update === "function" ? update(old || []) : update),
      );
    },
    [bookId, client],
  );
  const refresh = useCallback(async () => {
    await Promise.all([
      client.invalidateQueries({ queryKey: books.queryKey }),
      client.invalidateQueries({ queryKey: vocabulary.queryKey }),
      client.invalidateQueries({ queryKey: getListReadingsQueryKey(bookId) }),
    ]);
  }, [client, bookId, books.queryKey, vocabulary.queryKey]);
  return {
    books: books.data || emptyBooks,
    vocabulary: vocabulary.data || emptyVocabulary,
    readings: readings.data || emptyReadings,
    system: system.data,
    loading: owner.isPending || (owner.isSuccess && books.isPending),
    queryError:
      owner.error || books.error || vocabulary.error || readings.error,
    refresh,
    setReadings,
    checkSystem: () => system.refetch({ throwOnError: true }),
  };
}
