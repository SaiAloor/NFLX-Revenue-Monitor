from pathlib import Path

import pytest

from monitor.parse import ParseError, normalize_quarter, parse_letter

FIXTURE = (Path(__file__).parent / "fixtures" / "letter_q3_2026.html").read_text()


def test_reads_regions_totals_and_guidance():
    letter = parse_letter(FIXTURE)
    assert letter.quarters == ["Q3'25", "Q4'25", "Q1'26", "Q2'26", "Q3'26"]
    assert letter.regions["UCAN"] == [5072, 5339, 5245, 5432, 5628]
    assert letter.regions["APAC"][-1] == 1537
    assert letter.totals["Q3'26"] == 12874
    assert letter.guidance == {"Q4'26": 13442}


def test_curly_apostrophes_and_joined_dollar_cells():
    page = FIXTURE.replace("'", "’").replace("<td style=\"text-align:right\">$</td><td style=\"text-align:right\">", "<td>$")
    letter = parse_letter(page)
    assert letter.quarters[-1] == "Q3'26"
    assert letter.regions["EMEA"] == [3699, 3873, 3998, 4034, 4107]


def test_missing_value_is_an_error_not_a_guess():
    broken = FIXTURE.replace("5,628", "", 1)
    with pytest.raises(ParseError, match="UCAN revenue row"):
        parse_letter(broken)


def test_missing_regional_table():
    with pytest.raises(ParseError, match="Regional Breakdown"):
        parse_letter(FIXTURE.split("<p><b>Regional Breakdown")[0] + "</body></html>")


@pytest.mark.parametrize("text,expected", [("Q3'26", "Q3'26"), ("Q3’26", "Q3'26"), ("Q4 '25 Forecast", "Q4'25"), ("Revenue", None)])
def test_normalize_quarter(text, expected):
    assert normalize_quarter(text) == expected
