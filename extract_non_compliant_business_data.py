import pdfplumber
import pandas as pd
import re
import csv

pdf_path = "Businesses that have not complied with the money laundering regulations (2025 to 2026) - GOV.UK.pdf"

money_pattern = re.compile(r"^£([\d,]+\.\d{2})$")

# Column boundaries found from inspecting the PDF
bounds = [0, 200, 350, 520, 630, 842]

def get_text(words, x1, x2):
    words = [
        w for w in words
        if x1 <= w["x0"] < x2
    ]

    words.sort(key=lambda w: (w["top"], w["x0"]))

    return " ".join(w["text"] for w in words)

def parse_breach_numbers(description):
    match = re.match(r"^\(([\d,\s&]+)\)", description)

    if not match:
        # Handles the unusual "21(4) Breach..." entry
        match = re.match(r"^(\d+)\(\d+\)", description)

        if match:
            return (int(match.group(1)),)

        return ()

    numbers = re.findall(r"\d+", match.group(1))

    return tuple(int(n) for n in numbers)


def remove_breach_numbers(description):
    description = re.sub(
        r"^\([\d,\s&]+\)\s*",
        "",
        description
    )

    # unusual 21(4) case
    description = re.sub(
        r"^\d+\(\d+\)\s*",
        "",
        description
    )

    return description

rows = []

with pdfplumber.open(pdf_path) as pdf:

    for page in pdf.pages:

        # Ignore page header/footer
        words = [
            w for w in page.extract_words()
            if 65 <= w["top"] < 565
        ]

        # Penalty amounts identify logical rows
        penalties = [
            w for w in words
            if money_pattern.fullmatch(w["text"]) and w["x0"] > 500
        ]

        penalties.sort(key=lambda w: w["top"])

        if not penalties:
            continue

        # Text before first new row may be continuation
        # of previous page's final row
        if rows:
            first_y = penalties[0]["top"]

            continuation = [
                w for w in words
                if w["top"] < first_y
            ]

            for col in range(5):
                text = get_text(
                    continuation,
                    bounds[col],
                    bounds[col + 1]
                )

                if text:
                    rows[-1][col] += " " + text

        # Extract each logical row
        for i, penalty in enumerate(penalties):

            start = penalty["top"]

            if i + 1 < len(penalties):
                end = penalties[i + 1]["top"]
            else:
                end = 565

            row_words = [
                w for w in words
                if start - 0.2 <= w["top"] < end - 0.2
            ]

            row = [
                get_text(row_words, bounds[col], bounds[col + 1])
                for col in range(5)
            ]

            rows.append(row)


df = pd.DataFrame(
    rows,
    columns=[
        "company_name",
        "registered_address",
        "breach_description",
        "penalty_amount",
        "appeal_status"
    ]
)


df["breach_numbers"] = df["breach_description"].apply(
    parse_breach_numbers
)

df["breach_description"] = df["breach_description"].apply(
    remove_breach_numbers
)

df["penalty_amount_pounds"] = (
    df["penalty_amount"]
    .str.extract(money_pattern)
)

df = df.dropna(subset=["penalty_amount_pounds"])

df["penalty_amount_pounds"] = df["penalty_amount_pounds"].str.replace(",", "").astype(float)

df.to_csv(
    "non_compliant_businesses.csv",
    index=False,
    quoting=csv.QUOTE_MINIMAL
)