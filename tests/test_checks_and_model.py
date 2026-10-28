import pandas as pd

from monitor import checks, model, store
from monitor.parse import Letter

DATA = store.load_revenue()


def test_seed_data_passes_every_check():
    assert [i for i in checks.run_all(DATA) if i.level == "error"] == []


def test_reconciliation_flags_a_bad_total():
    bad = DATA.copy()
    bad.loc[bad["quarter"] == "Q2'26", "total"] += 50
    issues = checks.check_reconciliation(bad)
    assert len(issues) == 1 and "Q2'26" in issues[0].message


def test_known_gap_is_explained_not_failed():
    recon = model.reconciliation(DATA)
    assert recon.set_index("quarter").loc["Q3'23", "status"] == "explained"
    assert (recon["status"] == "MISMATCH").sum() == 0


def test_gap_in_quarters_is_an_error():
    issues = checks.check_continuity(DATA.drop(index=5))
    assert issues and issues[0].level == "error"


def test_restatement_is_detected():
    new = DATA[DATA["quarter"] == "Q3'26"].copy()
    new["UCAN"] += 10
    issues = checks.check_restatements(DATA, new)
    assert any("Q3'26 UCAN changed" in i.message for i in issues)


def test_next_quarter_rolls_over_the_year():
    assert model.next_quarter("Q3'26") == "Q4'26"
    assert model.next_quarter("Q4'26") == "Q1'27"


def test_forecast_matches_hand_calculation():
    target, fc = model.forecast_next(DATA)
    assert target == "Q4'26"
    ucan = fc.set_index("region").loc["UCAN", "forecast_musd"]
    expected = 5339 * ((5628 / 5072) + (5432 / 4929)) / 2
    assert ucan == round(expected)
    assert fc.set_index("region").loc["Total", "forecast_musd"] == 13570


def test_backtest_uses_only_past_data():
    bt = model.backtest(DATA)
    assert bt["quarter"].iloc[0] == "Q1'25"   # first quarter with six quarters of history
    assert len(bt) == len(DATA) - 6


def test_new_letter_adds_a_quarter_and_guidance():
    letter = Letter(
        quarters=["Q4'25", "Q1'26", "Q2'26", "Q3'26", "Q4'26"],
        regions={"UCAN": [5339, 5245, 5432, 5628, 5900], "EMEA": [3873, 3998, 4034, 4107, 4300],
                 "LATAM": [1418, 1497, 1584, 1603, 1700], "APAC": [1421, 1509, 1510, 1537, 1600]},
        totals={"Q4'25": 12051, "Q1'26": 12250, "Q2'26": 12560, "Q3'26": 12874, "Q4'26": 13500},
        guidance={"Q1'27": 13800},
    )
    merged = store.merge(DATA, store.letter_to_frame(letter))
    assert merged["quarter"].iloc[-1] == "Q4'26" and len(merged) == len(DATA) + 1
    assert merged.iloc[-1]["period_end"] == "2026-12-31"
    assert checks.run_all(merged) == []
    guidance = store.merge_guidance(store.load_guidance(), letter, "Q4'26", "test")
    acc = model.guidance_accuracy(merged, guidance).set_index("quarter")
    assert acc.loc["Q4'26", "actual_musd"] == 13500
    assert acc.loc["Q1'27", "guidance_musd"] == 13800
