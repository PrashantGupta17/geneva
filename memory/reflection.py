import chromadb
import uuid
from typing import List, Dict, Any
from core.schemas import ProjectDSL

class ReflectionMemory:
    """
    Manages semantic memory of past successful workflows using ChromaDB.
    This enables 'Experience Replay' for the Planner Agent.
    """
    def __init__(self, db_path: str = "./chroma_db"):
        self.client = chromadb.PersistentClient(path=db_path)
        self.collection = self.client.get_or_create_collection(
            name="successful_projects"
        )

    def store_success(self, natural_language_prompt: str, final_dsl: ProjectDSL):
        """
        Embeds and stores the original problem and the finalized YAML DSL.
        """
        doc_id = str(uuid.uuid4())

        # We store the YAML representation as metadata or text
        import yaml
        yaml_content = yaml.dump(final_dsl.model_dump(), sort_keys=False)

        self.collection.add(
            documents=[natural_language_prompt],
            metadatas=[{"yaml_dsl": yaml_content, "project_name": final_dsl.project_name}],
            ids=[doc_id]
        )
        print(f"Stored successful project '{final_dsl.project_name}' in ChromaDB.")

    def retrieve_similar_projects(self, natural_language_prompt: str, n_results: int = 2) -> str:
        """
        Queries ChromaDB for similar past problems and returns their YAML DSLs
        to be used as few-shot examples for the Planner.
        """
        if self.collection.count() == 0:
            return "No past examples found."

        results = self.collection.query(
            query_texts=[natural_language_prompt],
            n_results=min(n_results, self.collection.count())
        )

        examples = []
        docs = results.get('documents')
        metas = results.get('metadatas')
        if not docs or not docs[0] or not metas or not metas[0]:
            return "No past examples found."

        for i, doc in enumerate(docs[0]):
            meta = metas[0][i]
            examples.append(
                f"--- Past Problem ---\n{doc}\n"
                f"--- Successful DSL ---\n{meta['yaml_dsl']}\n"
            )

        return "\n".join(examples)

if __name__ == "__main__":
    # Test memory layer
    mem = ReflectionMemory()
    from core.schemas import ProjectDSL, StageDSL

    dummy_dsl = ProjectDSL(
        project_name="TestProject",
        global_budget=5.0,
        stages=[
            StageDSL(
                stage_name="Init",
                assigned_model_tier="free",
                stage_budget=1.0,
                success_criteria={"status": "ok"},
                requires_human_approval=False
            )
        ]
    )

    mem.store_success("Setup a simple test project to initialize systems.", dummy_dsl)
    print("Retrieving similar...")
    print(mem.retrieve_similar_projects("Initialize a basic project system."))
