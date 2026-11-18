from __future__ import annotations

from typing import Protocol, cast

from neo4j import GraphDatabase
from pydantic import JsonValue

from backend.app.core.config import Settings


class GraphStore(Protocol):
    def sync(
        self,
        book_id: str,
        job_id: str,
        entities: list[dict[str, JsonValue]],
        claims: list[dict[str, JsonValue]],
    ) -> None: ...
    def search(
        self, book_id: str, entity_ids: list[str], job_ids: list[str], allowed_passages: list[str]
    ) -> list[str]: ...


class Neo4jStore:
    def __init__(self, config: Settings) -> None:
        if not config.neo4j_password.get_secret_value():
            raise ValueError("Configure the Neo4j password before synchronizing knowledge")
        self.driver = GraphDatabase.driver(  # pyright: ignore[reportUnknownMemberType] -- driver's config kwargs are untyped
            config.neo4j_uri,
            auth=(config.neo4j_user, config.neo4j_password.get_secret_value()),
            connection_timeout=5,
        )

    def verify(self) -> None:
        self.driver.verify_connectivity()  # pyright: ignore[reportUnknownMemberType] -- driver's optional config is untyped

    def sync(
        self,
        book_id: str,
        job_id: str,
        entities: list[dict[str, JsonValue]],
        claims: list[dict[str, JsonValue]],
    ) -> None:
        try:
            _ = self.driver.execute_query(
                "CREATE CONSTRAINT knowledge_entity_id IF NOT EXISTS FOR (n:KnowledgeEntity) REQUIRE n.id IS UNIQUE"
            )
            _ = self.driver.execute_query(
                "CREATE CONSTRAINT knowledge_claim_id IF NOT EXISTS FOR (n:KnowledgeClaim) REQUIRE n.id IS UNIQUE"
            )
            # Replace only this job's projection, in a single Neo4j transaction.
            with self.driver.session() as session:  # pyright: ignore[reportUnknownMemberType] -- driver config kwargs are untyped
                with session.begin_transaction() as tx:
                    _ = tx.run(
                        "MATCH (c:KnowledgeClaim {book_id:$book,job_id:$job}) DETACH DELETE c",
                        book=book_id,
                        job=job_id,
                    ).consume()
                    _ = tx.run(
                        "UNWIND $entities AS e MERGE (n:KnowledgeEntity {id:e.id}) SET n.book_id=$book, n.name=e.name, n.kind=e.kind",
                        book=book_id,
                        entities=entities,
                    ).consume()
                    _ = tx.run(
                        """UNWIND $claims AS c
                        MATCH (s:KnowledgeEntity {id:c.subject,book_id:$book}), (o:KnowledgeEntity {id:c.object,book_id:$book})
                        MERGE (n:KnowledgeClaim {id:c.id})
                        SET n.book_id=$book,n.job_id=$job,n.relation=c.relation,n.evidence=c.evidence,n.description=c.description
                        MERGE (n)-[:SUBJECT]->(s) MERGE (n)-[:OBJECT]->(o)""",
                        book=book_id,
                        job=job_id,
                        claims=claims,
                    ).consume()
                    tx.commit()
        finally:
            self.driver.close()

    def search(
        self, book_id: str, entity_ids: list[str], job_ids: list[str], allowed_passages: list[str]
    ) -> list[str]:
        try:
            result = self.driver.execute_query(
                """
                MATCH (seed:KnowledgeEntity {book_id:$book}) WHERE seed.id IN $entities
                MATCH (seed)<-[:SUBJECT|OBJECT]-(first:KnowledgeClaim)-[:SUBJECT|OBJECT]->(other:KnowledgeEntity)
                WHERE first.book_id=$book AND first.job_id IN $jobs AND all(p IN first.evidence WHERE p IN $allowed)
                OPTIONAL MATCH (other)<-[:SUBJECT|OBJECT]-(second:KnowledgeClaim)
                WHERE second.book_id=$book AND second.job_id IN $jobs AND all(p IN second.evidence WHERE p IN $allowed)
                RETURN first.evidence + coalesce(second.evidence,[]) AS passages LIMIT 30
                """,
                book=book_id,
                entities=entity_ids,
                jobs=job_ids,
                allowed=allowed_passages,
            )
            passages: list[str] = []
            for record in result.records:
                value = cast(object, record["passages"])
                if isinstance(value, list):
                    passages.extend(item for item in cast(list[object], value) if isinstance(item, str))
            return list(dict.fromkeys(passages))[:40]
        finally:
            self.driver.close()
