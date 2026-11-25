from src.healthtech_resume_service import appointment_notification, parse_candidate


def test_unconfirmed_appointment_requires_staff_review():
    candidate = parse_candidate("Dr. Lin\nlin@example.org\nFHIR Python")
    assert candidate.name == "Dr. Lin"
    assert candidate.skills == ("FHIR", "Python")
    assert appointment_notification("needs_review").startswith("Appointment needs review")
    assert appointment_notification("unknown") == "Appointment status is pending. Staff review is required before notification."
