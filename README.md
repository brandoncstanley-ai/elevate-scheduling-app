# Elevate Scheduling: Capstone II v1 (Tier 4)

BUAD 583 · Brandon Stanley · Elevate Oral Surgery

This Streamlit app reads an oral surgery treatment plan and recommends how many minutes to book, from patient seated to discharged. It uses a rule-based plan reader and a linear regression model trained on 111 de-identified cases. It needs no API key and no external AI service.

The app has five tabs:

- **Desk:** reads the plan and recommends a block.
- **Day plan:** lays out the day across three assistant columns.
- **Record:** times a case by stage and refits the model.
- **Evaluation:** shows the held-out model results and the plan-reader test sets.
- **About:** describes the workflow and its limits.

## Files

| File | Contents |
|---|---|
| `app.py` | The Streamlit app |
| `plan_reader.py` | The rule-based treatment-plan reader |
| `test_plans.py` | Made-up test plans (development set and blind variants) |
| `elevate_cases.csv` | 111 de-identified cases (no names, initials, ages or dates) |

## Run locally

```
pip install -r requirements.txt
streamlit run app.py
```
