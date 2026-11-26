"""Unit tests for personal-data masking (AI2, N7).

Each case is a real sentence a client might say, and what the AI may see.
"""

import pytest

from projects.masking import mask_personal_data


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Email me at sam.lee+shop@gmail.com please.", "Email me at [EMAIL] please."),
        ("It's sam dot lee at gmail dot com.", "It's [EMAIL]."),
        ("Write to bookings at bakery dot co dot uk", "Write to [EMAIL]"),
        # How speech-to-text really wrote one in a live interview.
        ("you can get my email address which is samlee27 at the gmail.com in services", "you can get my email address which is [EMAIL] in services"),
        ("It's sam.lee at gmail.com", "It's [EMAIL]"),
        ("sam at gmail dot co dot uk", "[EMAIL]"),
    ],
)
def test_emails_are_masked(text, expected):
    assert mask_personal_data(text) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Call 07700 900123 any time.", "Call [PHONE] any time."),
        ("My number is +44 7700 900123.", "My number is [PHONE]."),
        ("The office is (020) 7946 0958.", "The office is [PHONE]."),
        ("Try 0161-496-0000 tomorrow.", "Try [PHONE] tomorrow."),
    ],
)
def test_phone_numbers_are_masked(text, expected):
    assert mask_personal_data(text) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("We're at 221B Baker Street, London.", "We're at [ADDRESS], London."),
        ("Deliver to 12 Station Road please.", "Deliver to [ADDRESS] please."),
        ("The postcode is SW1A 1AA.", "The postcode is [ADDRESS]."),
        ("our shop in g2 3ab is busy", "our shop in [ADDRESS] is busy"),
    ],
)
def test_addresses_are_masked(text, expected):
    assert mask_personal_data(text) == expected


@pytest.mark.parametrize(
    "text, expected",
    [
        ("Hi, my name is Sam Lee and I run a bakery.", "Hi, my name is [NAME] and I run a bakery."),
        ("My name's Priya.", "My name's [NAME]."),
        ("You can call me Jo.", "You can call me [NAME]."),
        ("Ask Mrs O'Neill about payroll.", "Ask Mrs [NAME] about payroll."),
        ("Dr. Ahmed Khan signs off orders.", "Dr. [NAME] signs off orders."),
        ("My business partner Tom handles deliveries.", "My business partner [NAME] handles deliveries."),
        ("Our accountant is called Mary-Jane.", "Our accountant is called [NAME]."),
    ],
)
def test_names_after_a_clue_are_masked(text, expected):
    assert mask_personal_data(text) == expected


def test_a_name_is_masked_everywhere_once_found():
    text = "My name is Sam Lee. Sam will approve orders, and Lee does the books."

    assert mask_personal_data(text) == (
        "My name is [NAME]. [NAME] will approve orders, and [NAME] does the books."
    )


def test_common_words_after_a_clue_are_not_treated_as_names():
    text = "Call me Monday. Speak to Mr Smith Then the team. Then we launch on Monday."

    assert mask_personal_data(text) == (
        "Call me Monday. Speak to Mr [NAME] Then the team. Then we launch on Monday."
    )


@pytest.mark.parametrize(
    "text",
    [
        "We sell 500 cakes a week for £3.50 each.",
        "We opened in 2019 and want to launch by March 2027.",
        "Customers book a slot between 9:30 and 17:00 on Monday.",
        "Staff log in, see today's orders and mark them as ready.",
        "About 1,200,000 visitors a year come to London.",
        "It must work on iPhone and Android.",
    ],
)
def test_ordinary_project_details_are_kept(text):
    assert mask_personal_data(text) == text


def test_masking_twice_changes_nothing():
    once = mask_personal_data("My name is Sam, email sam@shop.com, phone 07700 900123.")

    assert mask_personal_data(once) == once


def test_realistic_transcript():
    transcript = (
        "Hello, my name is Aisha Patel and I own a dog grooming salon at "
        "14 Mill Lane, Leeds LS1 4AB. Customers should book online and get a "
        "text reminder. Right now they phone me on 07911 123456 or email "
        "aisha at pawsome dot co dot uk. Aisha also wants a staff calendar."
    )

    masked = mask_personal_data(transcript)

    assert masked == (
        "Hello, my name is [NAME] and I own a dog grooming salon at "
        "[ADDRESS], Leeds [ADDRESS]. Customers should book online and get a "
        "text reminder. Right now they phone me on [PHONE] or email "
        "[EMAIL]. [NAME] also wants a staff calendar."
    )
    for secret in ("Aisha", "Patel", "Mill Lane", "LS1", "07911", "pawsome"):
        assert secret not in masked


def test_at_the_is_only_an_email_for_mail_providers():
    # "the" after "at" usually starts an ordinary phrase.
    text = "We deliver at the weekend."
    assert mask_personal_data(text) == text

