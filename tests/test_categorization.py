from surveycto_module_library.categorization import RuleCategorizer
from surveycto_module_library.config import load_settings


def test_rule_categories_are_ranked():
    categorizer = RuleCategorizer(load_settings().taxonomy_path)
    matches = categorizer.classify(
        "Are you currently enrolled in school and what grade are you in?"
    )
    assert matches[0].topic == "Education"
    assert matches[0].subtopic == "Enrollment and attendance"


def test_short_terms_do_not_match_inside_other_words():
    categorizer = RuleCategorizer(load_settings().taxonomy_path)
    matches = categorizer.classify("What was your wage last month?")
    matched_subtopics = {match.subtopic for match in matches}

    assert "Demographics" not in matched_subtopics
    assert "Employment" in matched_subtopics
