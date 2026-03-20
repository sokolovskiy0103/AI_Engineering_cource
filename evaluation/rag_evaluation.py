"""
Offline RAG evaluation pipeline for the parking lot assistant.

Run with:
    uv run python -m evaluation.rag_evaluation
"""

import json
from pathlib import Path

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from langchain.chat_models import init_chat_model
from langchain.embeddings import init_embeddings
from langchain_postgres import PGVector
from ragas import evaluate
from ragas.dataset_schema import SingleTurnSample, EvaluationDataset
from ragas.metrics import (
    LLMContextRecall,
    LLMContextPrecisionWithoutReference,
    Faithfulness,
    ResponseRelevancy,
)

from config import settings
from db.database import CONNECTION_STRING
from main import invoke

EVAL_DATASET_PATH = Path(__file__).parent / "eval_dataset.json"
RESULTS_PATH = Path(__file__).parent / "eval_results.json"


def load_eval_dataset() -> list[dict]:
    with open(EVAL_DATASET_PATH, encoding="utf-8") as f:
        return json.load(f)


def main():
    token_provider = get_bearer_token_provider(
        DefaultAzureCredential(),
        settings.azure_openai_scope,
    )
    llm = init_chat_model(
        settings.llm_model,
        azure_ad_token_provider=token_provider,
    )
    embedding = init_embeddings(
        settings.embedding_model,
        azure_ad_token_provider=token_provider,
    )
    vectorstore = PGVector(
        embeddings=embedding,
        collection_name="park_info_docs",
        connection=CONNECTION_STRING,
        create_extension=False,
    )

    eval_data = load_eval_dataset()
    samples: list[SingleTurnSample] = []

    print(f"Running evaluation on {len(eval_data)} samples...\n")

    for i, item in enumerate(eval_data, 1):
        question = item["question"]
        ground_truth = item["ground_truth"]
        answer, context = invoke(
            llm=llm,
            message=question,
            vectorstore=vectorstore,
            session_id='eval'
        )

        samples.append(SingleTurnSample(
            user_input=question,
            response=answer,
            retrieved_contexts=context,
            reference=ground_truth,
        ))


    dataset = EvaluationDataset(samples=samples)
    ragas_results = evaluate(
        dataset=dataset,
        metrics=[
            LLMContextRecall(),
            LLMContextPrecisionWithoutReference(),
            Faithfulness(),
            ResponseRelevancy(),
        ],
        llm=llm,
        embeddings=embedding,
    )

    print("\n--- RAGAS Metrics ---")
    df = ragas_results.to_pandas()
    metric_columns = [c for c in df.columns if c not in ("user_input", "response", "retrieved_contexts", "reference")]
    avg_scores = {col: df[col].mean() for col in metric_columns}
    for metric_name, score in avg_scores.items():
        print(f"  {metric_name}: {score:.4f}")

    output = {
        "ragas_metrics": {k: round(v, 4) for k, v in avg_scores.items()},
    }

    with open(RESULTS_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nDetailed results saved to {RESULTS_PATH}")


if __name__ == "__main__":
    main()
