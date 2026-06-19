# Skill: demo

Launch the full Loan Eligibility AI Agent demo stack.

## Usage
/demo

## Steps
```bash
pip install -r requirements.txt
streamlit run frontend/app.py
```

## Demo Script
1. Rahul Sharma, age 35, income 100000, EMI 10000, credit 760, Salaried, loan 500000 -> ELIGIBLE
2. Change credit to 580 -> NOT ELIGIBLE
3. Change age to 65 -> fast-path rejection
