from surveycto_module_library.demo import _education_form
from surveycto_module_library.modules import infer_modules
from surveycto_module_library.parsing import parse_definition


def test_parses_multilingual_groups_choices_and_dependencies():
    parsed = parse_definition(_education_form(), "fallback")
    assert parsed.form_id == "demo_education"
    assert len(parsed.groups) == 2
    assert sum(question.is_question for question in parsed.questions) == 5
    assert parsed.questions[0].labels["Arabic"].startswith("هل")
    assert any(item.target == "enrolled" for item in parsed.dependencies)
    assert len(parsed.choices) == 4


def test_group_modules_are_inferred():
    parsed = parse_definition(_education_form(), "fallback")
    modules = infer_modules(parsed)
    assert [module.label for module in modules] == [
        "School enrollment and attendance",
        "Employment and earnings",
    ]
