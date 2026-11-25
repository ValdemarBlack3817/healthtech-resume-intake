import json
import sys

from healthtech_resume_service import ResumeRequest, ingest_resume


def main() -> None:
    result = ingest_resume(ResumeRequest(sys.stdin.buffer.read(), "needs_review", "appt-demo"))
    print(json.dumps({"candidate": result.candidate.__dict__, "notification": result.notification, "vector_id": result.vector_id}))


if __name__ == "__main__":
    main()
