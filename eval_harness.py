import json
import csv
import time
import os
from src.pipeline import SagePipeline


EXPECTED_BENCHMARK = {
    "S01": {"expected_status": "answered", "key_citations": ["refunds-issue.md", "changelog.md"]},
    "S02": {"expected_status": "answered", "key_citations": ["invoice-attachments.md", "changelog.md"]},
    "S03": {"expected_status": "answered", "key_citations": ["api-rate-limits.md", "plan-limits.csv", "changelog.md"]},
    "S04": {"expected_status": "answered", "key_citations": ["changelog.md"]},
    "S05": {"expected_status": "answered", "key_citations": ["tax-eu-vat.md", "subscription-proration.md"]},
    "S06": {"expected_status": "abstained", "key_citations": []},
    "S07": {"expected_status": "abstained", "key_citations": []},
    "S08": {"expected_status": "refused", "key_citations": []},
    "S09": {"expected_status": "clarify", "key_citations": ["payouts-schedule.md", "payouts-faq.md", "plan-limits.csv"]},
}


def run_evaluation(num_runs=3, output_json="eval_results.json", output_csv="eval_results.csv"):
    print("=" * 70)
    print("           PAPERKITE SAGE QA - EVALUATION HARNESS")
    print("=" * 70)

    with open("sample_questions.json", "r", encoding="utf-8") as f:
        questions = json.load(f)

    pipeline = SagePipeline()
    results = []
    summary = {
        "total_questions": len(questions),
        "num_runs": num_runs,
        "passed": 0,
        "failed": 0,
        "consistent_decisions": 0,
        "avg_latency_ms": 0.0,
    }

    all_latencies = []

    for item in questions:
        qid = item["id"]
        q = item["question"]
        level = item["level"]
        bench_info = EXPECTED_BENCHMARK.get(qid, {"expected_status": "answered", "key_citations": []})
        expected_status = bench_info["expected_status"]

        print(f"\nEvaluating [{qid}] ({level.upper()}): '{q}'")

        question_runs = []
        statuses = []

        for run_idx in range(1, num_runs + 1):
            res = pipeline.ask(q, conversation_id=f"eval-{qid}-run-{run_idx}")
            run_data = {
                "run": run_idx,
                "question_id": qid,
                "question": q,
                "level": level,
                "status": res["status"],
                "status_label": res.get("status_label", res["status"]),
                "expected_status": expected_status,
                "answer": res["answer"],
                "citations": [c["doc_id"] for c in res.get("citations", [])],
                "conflicts_count": len(res.get("conflicts", [])),
                "model": res.get("model", "unknown"),
                "latency_ms": res.get("latency_ms", 0),
            }
            statuses.append(res["status"])
            all_latencies.append(res.get("latency_ms", 0))
            question_runs.append(run_data)
            results.append(run_data)

        # Check consistency across repeated runs
        is_consistent = len(set(statuses)) == 1
        if is_consistent:
            summary["consistent_decisions"] += 1

        primary_status = statuses[0]
        verdict = "PASS" if primary_status == expected_status else "FAIL"
        if verdict == "PASS":
            summary["passed"] += 1
        else:
            summary["failed"] += 1

        print(f"  -> Generated Status: {primary_status} | Expected: {expected_status} | Verdict: {verdict}")
        print(f"  -> Citations: {question_runs[0]['citations']}")
        print(f"  -> Consistency across {num_runs} runs: {'YES (100%)' if is_consistent else 'NO'}")
        print(f"  -> Latency: {question_runs[0]['latency_ms']}ms | Model: {question_runs[0]['model']}")

    summary["avg_latency_ms"] = round(sum(all_latencies) / len(all_latencies), 1) if all_latencies else 0.0

    # Save JSON report
    report = {
        "summary": summary,
        "runs": results,
    }
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    # Save CSV report
    fieldnames = [
        "question_id", "run", "level", "question", "status", "status_label",
        "expected_status", "model", "latency_ms", "citations", "conflicts_count", "answer"
    ]
    with open(output_csv, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            row = dict(r)
            row["citations"] = "; ".join(row["citations"])
            writer.writerow(row)

    print("\n" + "=" * 70)
    print("                     EVALUATION SUMMARY")
    print("=" * 70)
    print(f"Questions Evaluated: {summary['total_questions']}")
    print(f"Pass Rate:           {summary['passed']}/{summary['total_questions']} ({(summary['passed']/summary['total_questions'])*100:.1f}%)")
    print(f"Consistency Score:   {summary['consistent_decisions']}/{summary['total_questions']} ({(summary['consistent_decisions']/summary['total_questions'])*100:.1f}%)")
    print(f"Average Latency:     {summary['avg_latency_ms']} ms")
    print(f"Output Reports:      {output_json}, {output_csv}")
    print("=" * 70)

    return report


if __name__ == "__main__":
    run_evaluation(num_runs=3)
