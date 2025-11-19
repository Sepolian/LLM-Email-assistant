"""Sample runner for the LLM Email assistant.

This script demonstrates a dry-run pipeline:
 - fetch emails (stub)
 - summarize via LLM client (stub)
 - propose calendar events
 - (dry-run) print actions that would be taken

Run: python -m llm_email_app.main
"""
from llm_email_app.config import settings
from llm_email_app.email.gmail_client import GmailClient
from llm_email_app.llm.openai_client import OpenAIClient
from llm_email_app.calendar.gcal import GCalClient
from datetime import datetime, timezone


def run_sample_pipeline():
    print("Starting sample pipeline (dry-run=" + str(settings.DRY_RUN) + ")")

    gmail = GmailClient()
    openai = OpenAIClient()
    gcal = GCalClient()

    emails = gmail.fetch_recent_emails(max_results=3)
    for e in emails:
        print(f"\n--- Email from {e['from']}: {e['subject']}")
        summary = openai.summarize_email(e['body'], email_received_time=e.get('received'), current_time=datetime.now(timezone.utc).isoformat())
        print("Summary:\n", summary['text'])
        proposals = summary.get('proposals', [])
        for p in proposals:
            print("Proposed event:", p)
            if not settings.DRY_RUN:
                evt = gcal.create_event(p)
                print('Created event id:', evt)
            else:
                print('DRY RUN: would create event with:', p)

    return True


if __name__ == '__main__':
    run_sample_pipeline()
