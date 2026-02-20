"""
Radiologist productivity report generator.

This program reads a "Worklist" CSV file exported from your PACS.
It groups the exams by the "Approving Physician" (the radiologist).

For each radiologist, it creates ONE text file that contains TWO sections:
1) LAST HOUR        (what they approved in the last hour)
2) CUMULATIVE DAILY (what they approved since the start of the day)

Important behavior:
- If a radiologist has ZERO approved exams in the last hour, no report is generated for them.
- The timestamps in the CSV are treated as hospital-local time (by default: America/Los_Angeles).

Optional extras:
- Watch mode: keep running and re-process when a new CSV arrives.
- Email mode: send the generated reports as email attachments.

How to run (examples):
- Run once on a specific CSV:
    .\\.venv\\Scripts\\python.exe "src\\automatic report generation\\generate_radiologist_productivity_reports.py" ^
      --csv "src\\automatic report generation\\data\\Worklist-7-20260208_1211.csv"

- Run in a loop (watch the folder for new CSVs):
    .\\.venv\\Scripts\\python.exe "src\\automatic report generation\\generate_radiologist_productivity_reports.py" ^
      --watch --worklist-dir "D:\\Users\\script1\\Downloads" --prefix "Worklist-10-" --poll-seconds 10
"""

from __future__ import annotations  # Lets us use modern type hints in older Python versions.

import argparse  # Lets you run the script with options like --csv, --watch, and --send-email.
import re  # Helps us clean text (example: removing "PST" at the end of a timestamp).
import time  # Used for sleeping between checks in watch mode (a simple loop).
from dataclasses import dataclass  # A simple "container" for related values (like a small record).
from pathlib import Path  # Safer way to work with file/folder paths than plain strings.
from typing import Iterable, Optional  # Helps describe what functions expect and return.
import pytz  # Handles timezones like "America/Los_Angeles".

import pandas as pd  # Reads CSV files and makes it easy to group and filter the rows.


DEFAULT_DATA_TIMEZONE = "America/Los_Angeles"  # The timezone we assume the CSV timestamps are in.


# -----------------------------
# EMAIL SETTINGS (HARD-CODED FOR NOW)
# -----------------------------
# NOTE: Hard-coding credentials is not recommended. This is temporary for testing.
DEFAULT_SMTP_HOST = "p3plmcpnl504483.prod.phx3.secureserver.net"  # The email server (SMTP host).
DEFAULT_SMTP_PORT = 465  # The secure SSL port for sending email.
DEFAULT_SMTP_USER = "ans.imran@pacspros.llc"  # The email username (usually the email address).
DEFAULT_SMTP_PASS = "[oAywd(6CyxR"  # The email password (hard-coded for now).
DEFAULT_EMAIL_TO = [  # The default list of people who receive the email.
    "marko.malabanan@webzter.support",
    "info@webzter.support",
    "ansimran18@gmail.com",
]
DEFAULT_EMAIL_SUBJECT_PREFIX = "RADIOLOGIST REPORT"  # The start of the email subject line.

# -----------------------------------------------------------------------------
# WHO GETS WHICH RADIOLOGIST REPORT (EMAIL ROUTING)
# -----------------------------------------------------------------------------
# In plain words:
# - When the script generates a report for "Approving Physician = X",
#   we look up X in this dictionary.
# - If we find X, we send that radiologist's report ONLY to the email addresses
#   listed for X.
# - If we do NOT find X, we still send the report, but ONLY to the fallback
#   admin list (DEFAULT_EMAIL_TO), and we use a special subject line so you know
#   the dictionary needs to be updated.
PHYSICIAN_EMAIL_RECIPIENTS: dict[str, list[str]] = {
    "Morrell, Joseph M.D.": ["ansimran18@gmail.com", "info@webzter.support", "marko.malabanan@webzter.support"],
    "Pirani, Nadeer M.D.": ["ansimran18@gmail.com", "info@webzter.support", "marko.malabanan@webzter.support"],
    "Haas, Blake M.D.": ["ansimran18@gmail.com", "info@webzter.support", "marko.malabanan@webzter.support"],
    "Tank, Jay M.D.": ["ansimran18@gmail.com", "info@webzter.support", "marko.malabanan@webzter.support"],
    "Patel, Nirav M.D.": ["ansimran18@gmail.com", "info@webzter.support", "marko.malabanan@webzter.support"],
    "Quach,Pinf M.D.": ["ansimran18@gmail.com", "info@webzter.support", "marko.malabanan@webzter.support"],
    "Broome, Dale M.D.": ["ansimran18@gmail.com", "info@webzter.support", "marko.malabanan@webzter.support"],
    "Modica, Michael M.D.": ["ansimran18@gmail.com", "info@webzter.support", "marko.malabanan@webzter.support"],
    "Wang, James": ["ansimran18@gmail.com", "info@webzter.support", "marko.malabanan@webzter.support"],
    "Ellison, Brian MD": ["ansimran18@gmail.com", "info@webzter.support", "marko.malabanan@webzter.support"],
    "Wright, Joshua M.D.": ["ansimran18@gmail.com", "info@webzter.support", "marko.malabanan@webzter.support"],
    "Kostanian, Varoujan M.D.": ["ansimran18@gmail.com", "info@webzter.support", "marko.malabanan@webzter.support"],
    "Khan, Abrar M.D.": ["ansimran18@gmail.com", "info@webzter.support", "marko.malabanan@webzter.support"],
    "Tahir, Osman M.D.": ["ansimran18@gmail.com", "info@webzter.support", "marko.malabanan@webzter.support"],
    "Shroff, Sachin M.D.": ["ansimran18@gmail.com", "info@webzter.support", "marko.malabanan@webzter.support"],
    "Tew, Joshua": ["ansimran18@gmail.com", "info@webzter.support", "marko.malabanan@webzter.support"],
    "Tew, Joshua MD": ["ansimran18@gmail.com", "info@webzter.support", "marko.malabanan@webzter.support"],
    "Tew, Joshua M.D.": ["ansimran18@gmail.com", "info@webzter.support", "marko.malabanan@webzter.support"],
}


def _normalize_col(name: str) -> str:
    """
    Make a column name easier to match.

    People sometimes write the same column name with:
    - different capital letters (example: "Status" vs "status")
    - extra spaces (example: "Approved  Date" vs "Approved Date")

    This function converts the name into a simple, consistent form so we can compare it safely.
    """
    # Remove extra spaces, trim the ends, and make everything lowercase.
    return re.sub(r"\s+", " ", name.strip().lower())


def _find_column(df: pd.DataFrame, *candidates: str) -> Optional[str]:
    """
    Find the "real" column name in the CSV that matches one of our expected names.

    Example:
    - The CSV might say "Approving Physician"
    - Or it might say "approving physician"

    We try a list of names, and return the one that exists in the file.
    If we cannot find any match, we return None.
    """
    # Build a look-up table that maps a "cleaned" name to the original name in the file.
    normalized_to_original = {_normalize_col(c): c for c in df.columns}
    # Try each candidate name in order.
    for cand in candidates:
        # Convert the candidate to the same "clean" format and look it up.
        found = normalized_to_original.get(_normalize_col(cand))
        # If we found a match, return the real column name from the file.
        if found:
            return found
    # No candidate matched any column in the file.
    return None


def _slugify(text: str) -> str:
    """
    Turn a name into something safe to use in a filename.

    Example:
    - "Wright, Joshua M.D." becomes "Wright_Joshua_MD"

    This avoids characters that Windows filesystems don't like and keeps things consistent.
    """
    # Remove extra spaces at the start/end.
    text = text.strip()
    # If the text is empty, return a safe default.
    if not text:
        return "unknown"
    # Remove punctuation that can make filenames messy.
    text = re.sub(r"[^\w\s-]", "", text, flags=re.UNICODE)
    # Convert runs of spaces/dashes into a single underscore.
    text = re.sub(r"[\s-]+", "_", text).strip("_")
    # If we somehow end up empty, return a safe default.
    return text or "unknown"


def _find_latest_worklist_csv(folder: Path, prefix: str) -> Path:
    """
    Find the newest Worklist CSV file in a folder.

    "Newest" is decided by the file's modified time (Windows "LastWriteTime").
    This is usually more reliable than trying to read the timestamp from the filename.
    """
    # If the folder does not exist (or is not a folder), stop with a clear error.
    if not folder.exists() or not folder.is_dir():
        raise FileNotFoundError(f"Worklist folder not found: {folder}")

    # Find all CSV files whose name starts with the given prefix.
    candidates = list(folder.glob(f"{prefix}*.csv"))
    # If none exist, stop with a clear error.
    if not candidates:
        raise FileNotFoundError(f"No CSV files found starting with '{prefix}' in: {folder}")

    # Return the CSV that was modified most recently.
    return max(candidates, key=lambda p: p.stat().st_mtime)


_TRAILING_TZ_RE = re.compile(r"\s+[A-Z]{3,5}$")  # Matches a trailing timezone label like " PST" or " PDT".


def _parse_local_datetime(series: pd.Series, data_tz: pytz.BaseTzInfo) -> pd.Series:
    """
    Convert a column of date/time text into real date/time values in the hospital timezone.

    The CSV times often end with text like "PST" or "PDT". Pandas may not recognize those
    reliably, so we remove that ending and then "attach" the hospital timezone ourselves.
    """
    # Convert everything to text and remove extra spaces.
    cleaned = series.astype(str).str.strip()
    # Remove the trailing timezone label (example: " PST") so parsing is consistent.
    cleaned = cleaned.str.replace(_TRAILING_TZ_RE, "", regex=True)
    # Turn text into datetimes; if a value cannot be parsed, it becomes NaT (missing).
    # We use "mixed" format because these CSV files sometimes contain more than one style
    # of date/time text (example: "2026-02-07 06:04:00" AND "02/10/2026 2:03 AM").
    dt = pd.to_datetime(cleaned, errors="coerce", format="mixed")
    # Attach the timezone to the datetimes (treating them as already in local hospital time).
    return dt.dt.tz_localize(data_tz, ambiguous="NaT", nonexistent="shift_forward")


def _parse_report_end(value: str, data_tz: pytz.BaseTzInfo) -> pd.Timestamp:
    """
    Read the --report-end value (if provided) and convert it to the hospital timezone.

    If you give a time without a timezone, we treat it as hospital-local time.
    If you give a time with a timezone, we convert it into the hospital timezone.
    """
    # Clean the input by removing any trailing timezone text like " PST".
    cleaned = re.sub(_TRAILING_TZ_RE, "", value.strip())
    # Parse the string into a datetime (raise an error if it is not valid).
    ts = pd.to_datetime(cleaned, errors="raise")
    # If pandas returns a list-like object, make sure it contains only one value.
    if isinstance(ts, pd.DatetimeIndex):
        if len(ts) != 1:
            raise ValueError("Expected a single datetime value for --report-end.")
        ts = ts[0]
    # Ensure we have a pandas Timestamp object.
    if not isinstance(ts, pd.Timestamp):
        ts = pd.Timestamp(ts)
    # If the time has no timezone, attach the hospital timezone.
    if ts.tzinfo is None:
        return ts.tz_localize(data_tz, ambiguous="NaT", nonexistent="shift_forward")
    # If the time already has a timezone, convert it to the hospital timezone.
    return ts.tz_convert(data_tz)


def _compute_report_end(
    *,
    now: pd.Timestamp,
    data_tz: pytz.BaseTzInfo,
    report_end_override: Optional[str],
    hour_align: bool,
) -> pd.Timestamp:
    """
    Decide what time the report should be considered "ended".

    - If you pass --report-end, we use that.
    - Otherwise, we use the current time.
    - If --hour-align is enabled, we round down to the start of the hour.
    """
    # Choose the report end time: either the override, or "right now".
    report_end = _parse_report_end(report_end_override, data_tz) if report_end_override else now
    # Optionally "snap" the end time to the hour boundary (example: 07:00:00).
    if hour_align:
        report_end = report_end.floor("h")
    # Return the final chosen report end time.
    return report_end


def _format_dt(ts: Optional[pd.Timestamp]) -> str:
    """
    Turn a timestamp into the exact text format we want in the report.

    Format used:
    YYYY-MM-DD HH:MM:SS TZ
    Example:
    2026-02-07 07:00:00 PST
    """
    # If the value is missing, print an empty string in the report.
    if ts is None or pd.isna(ts):
        return ""
    # Make sure the value is a pandas Timestamp (so formatting works reliably).
    if not isinstance(ts, pd.Timestamp):
        ts = pd.Timestamp(ts)
    # Format it into a friendly report string.
    return ts.strftime("%Y-%m-%d %H:%M:%S %Z")


def _format_elapsed(delta: Optional[pd.Timedelta]) -> str:
    """
    Turn a time difference into a human-friendly sentence.

    Example:
    "4 hours 13 minutes 00 seconds"
    """
    # If the value is missing, print an empty string in the report.
    if delta is None or pd.isna(delta):
        return ""
    # Convert the whole timedelta into seconds (as a whole number).
    total_seconds = int(delta.total_seconds())
    # If it's negative, make it positive (so we do not show negative time).
    if total_seconds < 0:
        total_seconds = -total_seconds
    # Break seconds into hours, minutes, and seconds.
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    # Return the final readable text.
    return f"{hours} hours {minutes} minutes {seconds:02d} seconds"


def _format_rate(value: Optional[float]) -> str:
    """
    Format a number so it looks neat in the report (two decimal places).

    If the value is missing, return an empty string.
    """
    # If we do not have a value, leave the report field blank.
    if value is None:
        return ""
    # Try to format as a number with two decimals.
    try:
        return f"{float(value):.2f}"
    except Exception:
        # If anything goes wrong, return blank rather than crashing.
        return ""


def _format_rate_with_unit(value: Optional[float], unit: str) -> str:
    """
    Format a number and add a unit label after it.

    Example:
    "1.82 exams per hour"
    """
    # Format the number part first.
    base = _format_rate(value)
    # If we have a number, add the unit; otherwise return blank.
    return f"{base} {unit}" if base else ""


def _maybe_numeric(series: pd.Series) -> pd.Series:
    """
    Convert a column to numbers (when possible).

    Any values that cannot be converted become "missing" (NaN).
    This is useful when a column might be blank or text but we still want to sum it.
    """
    # Ask pandas to convert values to numbers; non-numbers become missing.
    return pd.to_numeric(series, errors="coerce")


def _clean_exam_type(series: pd.Series) -> pd.Series:
    """
    Clean up the exam description so it looks nicer in the report.

    Many study descriptions start with "- " (dash + space).
    We remove that so the list of exams is cleaner to read.
    """
    # Replace missing values with empty text, then remove a leading "- " and extra spaces.
    return series.fillna("").astype(str).str.replace(r"^\s*-\s*", "", regex=True).str.strip()


LABEL_WIDTH = 26  # How wide (in characters) the left-hand label column is in the report.
LINE_WIDTH = 60  # How wide the separator lines are (the rows of "=" and "-").


def _fmt_line(label: str, value: str) -> str:
    """
    Create one "Label : Value" line for the report.

    If the value is empty, we still print the label and the colon, but no value.
    This keeps the report layout consistent and easy to scan.
    """
    # If we have a value, print it after the colon.
    if value:
        return f"{label:<{LABEL_WIDTH}}: {value}"
    # If we do not have a value, print only the label and the colon.
    return f"{label:<{LABEL_WIDTH}}:"


@dataclass(frozen=True)
class ReportWindow:
    """
    A simple description of a time window used for a report section.

    Example windows:
    - LAST HOUR: from 06:00 to 07:00
    - CUMULATIVE DAILY: from 00:00 to the report end time
    """
    key: str  # A short internal name (used in code/filenames), like "last_hour".
    title: str  # The title shown in the report header, like "LAST HOUR".
    start: pd.Timestamp  # When this time window starts.
    end: pd.Timestamp  # When this time window ends.


def _render_report(
    *,
    physician: str,
    rows: pd.DataFrame,
    approved_ts_col: str,
    exam_type_col: str,
    window: ReportWindow,
    rvu_col: Optional[str],
    include_magic_footer: bool = True,
    include_elapsed_line: bool = True,
    include_average_lines: bool = True,
    include_first_last_lines: bool = True,
) -> str:
    """
    Build ONE report section as text (either "LAST HOUR" or "CUMULATIVE DAILY").

    Inputs in plain words:
    - physician: the radiologist's name
    - rows: the list of exams (rows) that belong to this radiologist and this time window
    - window: the start/end times for this report section

    The "include_*" switches let us hide fields in the LAST HOUR section
    (because you asked to keep that section simpler).
    """
    # Sort the exams by completion time so the list reads in chronological order.
    rows_sorted = rows.sort_values(approved_ts_col).copy()

    # Find the earliest and latest completed exam times in this section.
    first_ts = rows_sorted[approved_ts_col].min() if not rows_sorted.empty else None
    last_ts = rows_sorted[approved_ts_col].max() if not rows_sorted.empty else None

    # Calculate elapsed time between first and last exam (only if we plan to show it or use it).
    elapsed: Optional[pd.Timedelta] = None
    if (include_elapsed_line or include_average_lines) and (first_ts is not None and last_ts is not None):
        elapsed = last_ts - first_ts

    # Count how many completed exams are in this section.
    completed_exams = int(len(rows_sorted))

    # Compute averages only when requested (usually for the cumulative section).
    avg_exams_per_hour: Optional[float] = None
    elapsed_hours: Optional[float] = None
    if include_average_lines:
        # Convert the elapsed time into hours (as a number).
        if elapsed is not None and not pd.isna(elapsed):
            seconds = float(elapsed.total_seconds())
            elapsed_hours = (seconds / 3600.0) if seconds > 0 else None
        # Average exams/hour = total exams divided by hours between first and last exam.
        avg_exams_per_hour = (
            (completed_exams / elapsed_hours)
            if (elapsed_hours and completed_exams > 0)
            else (0.0 if completed_exams == 0 else None)
        )

    # RVU handling (placeholder unless an RVU column exists).
    completed_rvu: Optional[float] = None
    avg_rvu_per_hour: Optional[float] = None
    if rvu_col:
        # Convert RVU values to numbers so we can add them up.
        rows_sorted["_rvu_numeric"] = _maybe_numeric(rows_sorted[rvu_col])
        # Add up RVU for the exams in this section.
        completed_rvu = float(rows_sorted["_rvu_numeric"].sum(skipna=True))
        if include_average_lines:
            # Average RVU/hour uses the same elapsed-hours idea as exams/hour.
            avg_rvu_per_hour = (
                (completed_rvu / elapsed_hours)
                if (elapsed_hours and completed_rvu > 0)
                else (0.0 if completed_rvu == 0 else None)
            )

    # Start building the report text line-by-line.
    lines: list[str] = []
    # Section title (example: "RADIOLOGIST REPORT (LAST HOUR)").
    lines.append(f"RADIOLOGIST REPORT ({window.title})")
    # Top separator line.
    lines.append("=" * LINE_WIDTH)
    # Blank line for readability.
    lines.append("")
    # Radiologist name line.
    lines.append(_fmt_line("Radiologist name", physician))
    # Window start and end lines.
    lines.append(_fmt_line("Date/time report started", _format_dt(window.start)))
    lines.append(_fmt_line("Date/time report ended", _format_dt(window.end)))
    if include_first_last_lines:
        # First/last exam lines (only shown when requested).
        lines.append(_fmt_line("Date/time of first exam", _format_dt(first_ts)))
        lines.append(_fmt_line("Date/time of last exam", _format_dt(last_ts)))
    if include_elapsed_line:
        # Elapsed line (only shown when requested).
        lines.append(_fmt_line("Elapsed time first/last", _format_elapsed(elapsed)))
    # Completed exams count.
    lines.append(_fmt_line("Completed exams", str(completed_exams)))
    if include_average_lines:
        # Average exams/hour line (only shown when requested).
        lines.append(
            _fmt_line(
                "Average exams per hour",
                _format_rate_with_unit(avg_exams_per_hour, "exams per hour"),
            )
        )
    # Completed RVU (blank if we do not have an RVU column yet).
    lines.append(_fmt_line("Completed RVU", "" if completed_rvu is None else _format_rate(completed_rvu)))
    if include_average_lines:
        # Average RVU/hour line (only shown when requested).
        lines.append(
            _fmt_line(
                "Average RVU per hour",
                "" if avg_rvu_per_hour is None else _format_rate_with_unit(avg_rvu_per_hour, "RVU per hour"),
            )
        )
    # Separator line between header and the exam list.
    lines.append("-" * LINE_WIDTH)
    # Blank line for readability.
    lines.append("")
    # Table header for the exam list.
    lines.append(f"{'Completion date/time':<32}{'RVU':<9}Exam type")
    # Blank line before the rows.
    lines.append("")

    if rows_sorted.empty:
        # If there are no exams, print a friendly message.
        lines.append("(No completed exams in this period.)")
    else:
        # Otherwise, print each exam row.
        for _, row in rows_sorted.iterrows():
            # Completion time as text.
            dt_str = _format_dt(row[approved_ts_col])
            # RVU as text (blank if missing or not available).
            rvu_str = ""
            if rvu_col:
                val = row.get("_rvu_numeric")
                rvu_str = "" if pd.isna(val) else _format_rate(float(val))
            # Exam type/description.
            exam_type = str(row.get(exam_type_col, "")).strip()
            # Add the row to the report.
            lines.append(f"{dt_str:<32}{rvu_str:<9}{exam_type}")

    # Blank line before the ending separator.
    lines.append("")
    # Bottom separator line.
    lines.append("=" * LINE_WIDTH)
    if include_magic_footer:
        # Final footer (only included once at the end of the combined report).
        lines.append("END REPORT")
        lines.append("")
    # Join all lines into one block of text.
    return "\n".join(lines)


def _iter_physician_groups(df: pd.DataFrame, physician_col: str) -> Iterable[tuple[str, pd.DataFrame]]:
    """
    Yield the data grouped by radiologist.

    In plain words:
    - We look at the "Approving Physician" column.
    - We group the rows by that name.
    - We return one group at a time: (doctor_name, only_their_rows)
    """
    # Group the table by the physician name (and sort for consistent order).
    for physician, physician_df in df.groupby(physician_col, sort=True):
        # Convert the name to clean text (and remove extra spaces).
        physician_str = str(physician).strip()
        # Skip empty or missing names.
        if not physician_str or physician_str.lower() == "nan":
            continue
        # Return the name and their rows.
        yield physician_str, physician_df


def _parse_email_list(values: list[str]) -> list[str]:
    """
    Read email addresses from command-line inputs.

    We allow:
    - repeated flags: --email-to a@x.com --email-to b@x.com
    - comma-separated lists: --email-to "a@x.com,b@x.com"

    We also remove duplicates (so the same person doesn't get two copies).
    """
    # This will hold every email address we find.
    items: list[str] = []
    # Each entry might be one address or many separated by commas.
    for raw in values:
        for part in raw.split(","):
            part = part.strip()
            if part:
                items.append(part)
    # Deduplicate while keeping the original order.
    seen: set[str] = set()
    deduped: list[str] = []
    for item in items:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    # Return the cleaned list of recipients.
    return deduped


def _normalize_physician_name(name: str) -> str:
    """
    Normalize a physician name so we can match it reliably.

    Why this exists:
    - Real data can have small differences like:
      - "Quach,Pinf M.D." vs "Quach, Pinf M.D."
      - "M.D." vs "MD"
      - extra spaces

    We do a very simple cleanup so these small differences do not break email routing.
    """
    # Convert to text and trim spaces.
    name = str(name).strip()
    # Make matching case-insensitive by using uppercase.
    name = name.upper()
    # Remove dots so "M.D." and "MD" become the same.
    name = name.replace(".", "")
    # Normalize spaces (turn many spaces into one).
    name = re.sub(r"\s+", " ", name)
    # Normalize commas (remove spaces around commas).
    name = re.sub(r"\s*,\s*", ",", name)
    # Return the normalized name.
    return name


def _lookup_physician_recipients(physician: str) -> Optional[list[str]]:
    """
    Return the email recipients for a given radiologist (Approving Physician).

    - If the physician is in PHYSICIAN_EMAIL_RECIPIENTS, we return their email list.
    - If not, we return None (so the caller can use the fallback admin list).
    """
    # Normalize the name coming from the CSV.
    target = _normalize_physician_name(physician)
    # Compare against every key in the dictionary (also normalized).
    for key_name, emails in PHYSICIAN_EMAIL_RECIPIENTS.items():
        if _normalize_physician_name(key_name) == target:
            # Clean and deduplicate the list before returning it.
            return _parse_email_list(list(emails))
    # Not found in the dictionary.
    return None


@dataclass(frozen=True)
class EmailSettings:
    """
    A small bundle of email settings used to send the reports.

    This keeps the email details in one place so the rest of the code stays simple.
    """
    smtp_host: str  # The email server address (SMTP host).
    smtp_port: int  # The email server port (465 is common for secure SSL).
    smtp_user: str  # The username for logging into the email server.
    smtp_pass: str  # The password for logging into the email server.
    from_addr: str  # The "From" email address people see.
    to_addrs: list[str]  # The list of recipients ("To" addresses).
    subject_prefix: str  # The beginning of the email subject line.


def _send_email(
    *,
    settings: EmailSettings,
    subject: str,
    body: str,
    attachments: list[Path],
) -> None:
    """
    Send an email with the generated report files attached.

    - The email body is plain text (simple and readable).
    - Each report file is attached as a .txt file.
    """
    # Import email tools from the Python standard library.
    import smtplib
    from email.message import EmailMessage

    # Create a new email message.
    msg = EmailMessage()
    # Who the email is from.
    msg["From"] = settings.from_addr
    # Who receives the email.
    msg["To"] = ", ".join(settings.to_addrs)
    # The subject line of the email.
    msg["Subject"] = subject
    # The main email text (plain text).
    msg.set_content(body)

    # Attach each report file (if we can read it).
    for path in attachments:
        try:
            # Read the file as bytes so we can attach it.
            data = path.read_bytes()
        except Exception:
            # If a file cannot be read, skip it rather than failing the whole email.
            continue
        # Add the attachment to the email.
        msg.add_attachment(
            data,
            maintype="text",
            subtype="plain",
            filename=path.name,
        )

    # Connect to the email server securely and send the message.
    with smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port) as server:
        # Log in to the SMTP server.
        server.login(settings.smtp_user, settings.smtp_pass)
        # Send the email.
        server.send_message(msg)


@dataclass(frozen=True)
class GeneratedReport:
    """
    One finished combined report for one radiologist.

    We store:
    - physician: the radiologist name (Approving Physician)
    - path: where the .txt file was written
    - text: the full text inside the report file

    This makes it easy to both:
    - write the file, and
    - email the same exact content.
    """

    physician: str  # Radiologist name.
    path: Path  # Where the report text file lives.
    text: str  # The full report text.


def _generate_combined_reports(
    *,
    csv_path: Path,
    out_dir: Path,
    data_tz: pytz.BaseTzInfo,
    report_end: pd.Timestamp,
) -> list[GeneratedReport]:
    """
    Create the combined report files (one per radiologist).

    What this does, in plain words:
    1) Read the CSV file.
    2) Keep only "Approved" exams with a valid Approved Date and a radiologist name.
    3) Split the exams by radiologist (Approving Physician).
    4) For each radiologist:
       - Build a LAST HOUR section (simple)
       - Build a CUMULATIVE DAILY section (more detailed)
       - Save both sections into one combined .txt file

    Returns:
    - A list of GeneratedReport objects (who it is for + file path + full text).
    """
    # Make sure the CSV file exists before we try to read it.
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV not found: {csv_path}")

    # Read the CSV into a table (DataFrame).
    df = pd.read_csv(csv_path)

    # Figure out the exact column names in THIS CSV file.
    physician_col = _find_column(df, "Approving Physician", "approving physician")
    approved_date_col = _find_column(df, "Approved Date", "approved date")
    exam_type_col = _find_column(df, "Study Description", "study description", "Exam type", "exam type")
    status_col = _find_column(df, "Status", "status")

    # If key columns are missing, we cannot trust the report, so we stop.
    missing_cols = [
        name
        for name, col in [
            ("Approving Physician", physician_col),
            ("Approved Date", approved_date_col),
            ("Study Description", exam_type_col),
        ]
        if col is None
    ]
    if missing_cols:
        missing_str = ", ".join(missing_cols)
        raise ValueError(f"Missing required columns: {missing_str}")

    # RVU is optional for now; if it's missing, we keep RVU fields blank.
    rvu_col = _find_column(df, "RVU", "rvu")

    # Work on a copy so we do not accidentally change the original data.
    df = df.copy()
    # Make exam descriptions look nicer.
    df[exam_type_col] = _clean_exam_type(df[exam_type_col])
    # Parse the Approved Date into real timezone-aware timestamps.
    df["_approved_ts"] = _parse_local_datetime(df[approved_date_col], data_tz)
    # Drop rows where we could not parse the Approved Date.
    df = df[df["_approved_ts"].notna()]

    # Drop rows where the physician name is missing.
    df = df[df[physician_col].notna()].copy()
    # Clean the physician name text.
    df[physician_col] = df[physician_col].astype(str).str.strip()
    # Drop rows where the physician name is empty after cleaning.
    df = df[df[physician_col] != ""]

    # If we have a Status column, keep only rows that are truly "Approved".
    if status_col:
        df[status_col] = df[status_col].astype(str).str.strip()
        df = df[df[status_col].str.lower() == "approved"]

    # Decide the two windows we want to show in the combined report.
    start_of_day = report_end.normalize()
    start_last_hour = report_end - pd.Timedelta(hours=1)

    # Window #1: last hour.
    last_hour_window = ReportWindow(key="last_hour", title="LAST HOUR", start=start_last_hour, end=report_end)
    # Window #2: since midnight (start of day) until report end.
    cumulative_window = ReportWindow(
        key="cumulative_daily",
        title="CUMULATIVE DAILY",
        start=start_of_day,
        end=report_end,
    )

    # Ensure the output folder exists.
    out_dir.mkdir(parents=True, exist_ok=True)

    # Use the report date in the filename (example: 2026-02-07__Wright_Joshua_MD__combined.txt).
    run_date = report_end.strftime("%Y-%m-%d")
    # Keep track of the files we successfully wrote.
    written: list[GeneratedReport] = []

    # Process one radiologist at a time.
    for physician, physician_df in _iter_physician_groups(df, physician_col):
        # Make a clean filename-friendly version of their name.
        physician_slug = _slugify(physician)
        # Build the final output file path.
        out_path = out_dir / f"{run_date}__{physician_slug}__combined.txt"

        # Filter this radiologist's exams down to only the last hour.
        last_hour_df = physician_df[
            (physician_df["_approved_ts"] >= last_hour_window.start)
            & (physician_df["_approved_ts"] < last_hour_window.end)
        ].copy()

        # If they did nothing in the last hour, do not generate a report for them.
        if last_hour_df.empty:
            try:
                # Also remove any old/stale report file from a previous run.
                out_path.unlink(missing_ok=True)
            except Exception:
                # If delete fails (for example, file locked), ignore it.
                pass
            continue

        # Filter this radiologist's exams down to the cumulative daily window.
        cumulative_df = physician_df[
            (physician_df["_approved_ts"] >= cumulative_window.start)
            & (physician_df["_approved_ts"] < cumulative_window.end)
        ].copy()

        # Build the LAST HOUR section (simple layout).
        last_hour_text = _render_report(
            physician=physician,
            rows=last_hour_df,
            approved_ts_col="_approved_ts",
            exam_type_col=exam_type_col,
            window=last_hour_window,
            rvu_col=rvu_col,
            include_magic_footer=False,
            include_elapsed_line=False,
            include_average_lines=False,
            include_first_last_lines=False,
        ).rstrip()

        # Build the CUMULATIVE DAILY section (more detailed, and includes the final END REPORT footer).
        cumulative_text = _render_report(
            physician=physician,
            rows=cumulative_df,
            approved_ts_col="_approved_ts",
            exam_type_col=exam_type_col,
            window=cumulative_window,
            rvu_col=rvu_col,
            include_magic_footer=True,
        ).rstrip()

        # Combine both sections into one file (with a little spacing in between).
        combined_text = f"{last_hour_text}\n\n\n{cumulative_text}\n"

        # Write the combined report to disk.
        out_path.write_text(combined_text, encoding="utf-8")
        # Remember that we wrote this file (and what it contains).
        written.append(GeneratedReport(physician=physician, path=out_path, text=combined_text))

    # Return the list of report files we created.
    return written


def main() -> int:
    """
    Run the program (this is what happens when you "run the script").

    In plain words, this function:
    - Reads the options you pass in the command (like --csv or --watch).
    - Figures out what CSV file to use.
    - Generates the combined radiologist reports.
    - Optionally emails those reports.
    - Optionally keeps running in a loop (watch mode).
    """
    # Find the folder where this Python file lives.
    script_dir = Path(__file__).resolve().parent
    # Default folder where worklist CSVs live (a "data" folder next to this script).
    default_worklist_dir = script_dir / "data"
    # Default folder where the generated reports will be written.
    default_out_dir = default_worklist_dir / "radiologist_reports"

    # Build the command-line interface (so you can run: python script.py --csv ...).
    parser = argparse.ArgumentParser(  # Create the helper that reads your command-line options.
        description=(  # This is the short message shown when you run the script with --help.
            "Generate per-radiologist productivity reports from a Worklist*.csv export "
            "(last hour + cumulative daily), grouped by Approving Physician."
        )
    )
    # Option: choose a specific CSV file.
    parser.add_argument(  # Add the "--csv" option.
        "--csv",  # You type this to point to one specific CSV file.
        type=Path,  # Treat the value like a file path.
        default=None,  # If you do not provide it, we will pick the newest CSV from a folder.
        # This text is shown when you run the script with --help.
        help="Path to a Worklist CSV file. If omitted, the newest matching CSV in --worklist-dir is used.",
    )
    # Option: which folder to scan when --csv is not provided.
    parser.add_argument(  # Add the "--worklist-dir" option.
        "--worklist-dir",  # The folder we search for the newest CSV.
        type=Path,  # Treat the value like a folder path.
        default=default_worklist_dir,  # If omitted, use the built-in default folder.
        # This text is shown when you run the script with --help.
        help="Folder to scan for the newest Worklist*.csv when --csv is not provided.",
    )
    # Option: what the CSV filename should start with when scanning.
    parser.add_argument(  # Add the "--prefix" option.
        "--prefix",  # Only files that start with this text will be considered.
        type=str,  # This option is plain text.
        default="Worklist-7-",  # Default is the common naming pattern you use.
        # This text is shown when you run the script with --help.
        help="Filename prefix to match when scanning --worklist-dir (default: Worklist-7-).",
    )
    # Option: where to write the report text files.
    parser.add_argument(  # Add the "--out-dir" option.
        "--out-dir",  # The folder where we will save the report text files.
        type=Path,  # Treat the value like a folder path.
        default=default_out_dir,  # If omitted, use the built-in default report folder.
        # This text is shown when you run the script with --help.
        help="Output folder for generated report .txt files.",
    )
    # Option: what timezone the CSV timestamps are in.
    parser.add_argument(  # Add the "--data-timezone" option.
        "--data-timezone",  # The timezone name for the times shown in the CSV file.
        type=str,  # This option is plain text.
        default=DEFAULT_DATA_TIMEZONE,  # Default is the hospital's timezone.
        # This text is shown when you run the script with --help.
        help=f"Timezone name for the CSV times (default: {DEFAULT_DATA_TIMEZONE}).",
    )
    # Option: manually set the "report ended" time (useful for testing/reproducing past output).
    parser.add_argument(  # Add the "--report-end" option.
        "--report-end",  # Lets you pretend "now" is some specific time.
        type=str,  # This option is plain text (a date/time string).
        default=None,  # If omitted, we use the actual current time.
        # This text is shown when you run the script with --help.
        help=(
            "Set the 'report ended' time (in the same timezone as the CSV). "
            "Example: '2026-02-07 07:00:00'. If omitted, uses the current time."
        ),
    )
    # Option: snap the report end time to the hour boundary (example: 07:00:00).
    parser.add_argument(  # Add the "--hour-align" option.
        "--hour-align",  # When enabled, we round the report end time down to the hour.
        action="store_true",  # This makes it a simple on/off switch.
        default=True,  # Default ON (hourly buckets like 07:00-08:00).
        # This text is shown when you run the script with --help.
        help="Floor the report end time to the hour boundary (default: on).",
    )
    # Option: turn OFF hour alignment (mainly for debugging/testing).
    parser.add_argument(  # Add the "--no-hour-align" option.
        "--no-hour-align",  # When enabled, we do NOT floor the report time to the hour.
        dest="hour_align",  # Store the result in the same variable as --hour-align.
        action="store_false",  # This makes it an on/off switch (off).
        # This text is shown when you run the script with --help.
        help="Do not floor the report end time to the hour boundary.",
    )
    # Option: keep running forever and re-run when a new CSV arrives.
    parser.add_argument(  # Add the "--watch" option.
        "--watch",  # When enabled, the script keeps running.
        action="store_true",  # This makes it a simple on/off switch.
        # This text is shown when you run the script with --help.
        help="Run in a loop and process the newest matching CSV whenever it changes.",
    )
    # Option: how often to check for new CSV files in watch mode.
    parser.add_argument(  # Add the "--poll-seconds" option.
        "--poll-seconds",  # How often we check for a new file.
        type=int,  # This option is a whole number.
        default=10,  # Default is every 10 seconds.
        # This text is shown when you run the script with --help.
        help="Polling interval (seconds) for --watch mode.",
    )
    # Option: email the generated report files.
    parser.add_argument(  # Add the "--send-email" option.
        "--send-email",  # When enabled, the script sends an email after generating reports.
        action="store_true",  # This makes it a simple on/off switch.
        # This text is shown when you run the script with --help.
        help="Email the generated combined reports (as .txt attachments).",
    )
    # Option: SMTP host (email server).
    parser.add_argument(  # Add the "--smtp-host" option.
        "--smtp-host",  # The email server address (SMTP host).
        type=str,  # This option is plain text.
        default=DEFAULT_SMTP_HOST,  # If omitted, use the hard-coded default.
        # This text is shown when you run the script with --help.
        help="SMTP host for email sending.",
    )
    # Option: SMTP port (secure SSL is usually 465).
    parser.add_argument(  # Add the "--smtp-port" option.
        "--smtp-port",  # The port number used to connect to the email server.
        type=int,  # This option is a whole number.
        default=DEFAULT_SMTP_PORT,  # If omitted, use the hard-coded default.
        # This text is shown when you run the script with --help.
        help="SMTP port for SSL (default: 465).",
    )
    # Option: SMTP username (usually your email address).
    parser.add_argument(  # Add the "--smtp-user" option.
        "--smtp-user",  # The username to log into the email server.
        type=str,  # This option is plain text.
        default=DEFAULT_SMTP_USER,  # If omitted, use the hard-coded default.
        # This text is shown when you run the script with --help.
        help="SMTP username (usually your email address).",
    )
    # Option: SMTP password.
    parser.add_argument(  # Add the "--smtp-pass" option.
        "--smtp-pass",  # The password to log into the email server.
        type=str,  # This option is plain text.
        default=DEFAULT_SMTP_PASS,  # If omitted, use the hard-coded default.
        # This text is shown when you run the script with --help.
        help="SMTP password (hard-coded default; replace or pass here).",
    )
    # Option: override the "From" email address (defaults to --smtp-user).
    parser.add_argument(  # Add the "--email-from" option.
        "--email-from",  # The "From" address people see in the email.
        type=str,  # This option is plain text.
        default=None,  # If omitted, we use the SMTP username as the From address.
        # This text is shown when you run the script with --help.
        help="From address (defaults to --smtp-user).",
    )
    # Option: add one or more recipients.
    parser.add_argument(  # Add the "--email-to" option.
        "--email-to",  # Who receives the email (you can repeat this option).
        action="append",  # This lets you provide the option more than once.
        default=[],  # If omitted, we use the hard-coded default recipient list.
        # This text is shown when you run the script with --help.
        help=(
            "Fallback recipient email address used ONLY when a physician name is not found in "
            "PHYSICIAN_EMAIL_RECIPIENTS (repeatable, or comma-separated)."
        ),
    )
    # Option: control the start of the email subject line.
    parser.add_argument(  # Add the "--email-subject-prefix" option.
        "--email-subject-prefix",  # The beginning of the subject line.
        type=str,  # This option is plain text.
        default=DEFAULT_EMAIL_SUBJECT_PREFIX,  # If omitted, use the hard-coded default.
        # This text is shown when you run the script with --help.
        help="Email subject prefix.",
    )
    # Parse the options the user typed.
    args = parser.parse_args()

    # Convert the timezone name into a real timezone object.
    try:
        data_tz = pytz.timezone(args.data_timezone)
    except Exception as e:
        # If the timezone is not valid, stop with a clear message.
        print(f"ERROR: Invalid --data-timezone '{args.data_timezone}': {e}")
        return 2

    # Prepare email settings if the user asked to send email.
    email_settings: Optional[EmailSettings] = None
    if args.send_email:
        # IMPORTANT:
        # - We now route emails using PHYSICIAN_EMAIL_RECIPIENTS (one email per radiologist).
        # - The --email-to list is kept as a FALLBACK "admin" list only.
        #   It is used when a physician name is not found in the dictionary.
        admin_to_addrs = _parse_email_list(args.email_to) if args.email_to else list(DEFAULT_EMAIL_TO)

        # Pick the "From" address.
        from_addr = args.email_from or args.smtp_user
        if not admin_to_addrs:
            # No fallback recipients means we cannot send "unknown physician" emails safely.
            print("ERROR: --send-email requires at least one fallback recipient (use --email-to).")
        elif not args.smtp_pass or args.smtp_pass.strip().upper() == "CHANGE_ME":
            # Missing password means we cannot log in to the email server.
            print("ERROR: SMTP password not set. Update DEFAULT_SMTP_PASS or pass --smtp-pass.")
        else:
            # Store all email settings together.
            email_settings = EmailSettings(
                smtp_host=args.smtp_host,
                smtp_port=int(args.smtp_port),
                smtp_user=args.smtp_user,
                smtp_pass=args.smtp_pass,
                from_addr=from_addr,
                # This is the fallback "admin" recipient list.
                to_addrs=admin_to_addrs,
                subject_prefix=args.email_subject_prefix,
            )

    def process_csv(csv_path: Path) -> list[GeneratedReport]:
        """
        Process ONE CSV file:
        - Decide the report end time
        - Generate report files
        - Optionally send an email with attachments
        """
        # Get the current time in the hospital timezone.
        now = pd.Timestamp.now(tz=data_tz)
        # Decide what time the report should be considered "ended".
        report_end = _compute_report_end(
            now=now,
            data_tz=data_tz,
            report_end_override=args.report_end,
            hour_align=bool(args.hour_align),
        )

        # Generate the combined report files.
        written = _generate_combined_reports(
            csv_path=csv_path,
            out_dir=args.out_dir,
            data_tz=data_tz,
            report_end=report_end,
        )

        # Print a small summary to the terminal.
        print(f"CSV: {csv_path}")
        print(f"Data timezone: {args.data_timezone}")
        print(f"Now (data tz): {now.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        print(f"Report time (data tz): {report_end.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        # Also show the window used for the "last hour" report part (so it is easy to debug).
        last_hour_start = report_end - pd.Timedelta(hours=1)
        print(
            "Last hour window (data tz): "
            f"{last_hour_start.strftime('%Y-%m-%d %H:%M:%S %Z')} "
            f"to {report_end.strftime('%Y-%m-%d %H:%M:%S %Z')}"
        )
        print(f"Output folder: {args.out_dir}")
        print("Reports written:")
        # If nothing was written, say that clearly (so it doesn't look "stuck").
        if not written:
            print(" - (none)")
            print(
                "Reason: no radiologist had any approved exams inside the last hour window, "
                "so there was nothing to report."
            )
        else:
            for rep in written:
                print(f" - {rep.path}")

        # If email is enabled and we wrote at least one report, send emails.
        # We send ONE email PER radiologist (using PHYSICIAN_EMAIL_RECIPIENTS).
        if email_settings and written:
            # Send each radiologist their own report email.
            for rep in written:
                # Look up recipients from the routing dictionary.
                mapped_to = _lookup_physician_recipients(rep.physician)

                # Decide who should receive this email.
                missing_in_dictionary = not mapped_to
                to_addrs = mapped_to if mapped_to else list(email_settings.to_addrs)

                # Build the subject line (no timestamps, as requested).
                if missing_in_dictionary:
                    # Special subject so you know the dictionary needs to be updated.
                    subject = f"{email_settings.subject_prefix} - MISSING EMAIL MAP - {rep.physician.upper()}"
                else:
                    subject = f"{email_settings.subject_prefix} - {rep.physician.upper()}"

                # Build the email body:
                # - Top: the full combined report text (exactly what is in the file).
                # - Bottom: the old "CSV/report time/attachments" info (moved to the bottom, as requested).
                bottom_lines: list[str] = []
                if missing_in_dictionary:
                    bottom_lines.extend(
                        [
                            "",
                            "NOTE: This physician name was not found in the PHYSICIAN_EMAIL_RECIPIENTS dictionary.",
                            "      This email was sent to the fallback admin list instead.",
                        ]
                    )
                bottom_lines.extend(
                    [
                        "",
                        f"CSV: {csv_path}",
                        f"Report time: {report_end.strftime('%Y-%m-%d %H:%M:%S %Z')}",
                        "",
                        "Attached reports:",
                        f"- {rep.path.name}",
                        "",
                    ]
                )

                body = rep.text.rstrip("\n") + "\n" + "\n".join(bottom_lines)

                # Create a per-email settings object with the right "To" list.
                send_settings = EmailSettings(
                    smtp_host=email_settings.smtp_host,
                    smtp_port=email_settings.smtp_port,
                    smtp_user=email_settings.smtp_user,
                    smtp_pass=email_settings.smtp_pass,
                    from_addr=email_settings.from_addr,
                    to_addrs=to_addrs,
                    subject_prefix=email_settings.subject_prefix,
                )

                # Send this one email with one attachment.
                _send_email(
                    settings=send_settings,
                    subject=subject,
                    body=body,
                    attachments=[rep.path],
                )

                # Let the user know it worked (once per radiologist).
                print(f"Email sent for: {rep.physician}")
        elif email_settings and not written:
            # If there were no reports (example: nobody did work in the last hour), skip email.
            print("No reports written (skipping email).")

        # Return the list of files we created (useful for logging/testing).
        return written

    # If watch mode is enabled, we loop forever.
    if args.watch:
        # In watch mode we do not allow --csv, because we need to pick the latest file repeatedly.
        if args.csv is not None:
            print("ERROR: --watch cannot be used with --csv (use --worklist-dir/--prefix instead).")
            return 2

        # Keep a simple signature of the last processed file (path + modified time + size).
        last_sig: tuple[str, float, int] | None = None
        # Loop forever (until you stop the program).
        while True:
            try:
                # Print a tiny heartbeat message each time we "poll" the folder,
                # so it is obvious the script is alive and checking again.
                print("ok", flush=True)

                # Find the newest matching CSV in the worklist folder.
                latest = _find_latest_worklist_csv(args.worklist_dir, args.prefix)
                # Read file info (modified time and file size).
                st = latest.stat()
                # Build a quick "signature" so we can detect changes.
                sig = (str(latest), float(st.st_mtime), int(st.st_size))
                # If it's different than last time, process it.
                if sig != last_sig:
                    process_csv(latest)
                    last_sig = sig
            except Exception as e:
                # Do not crash the watcher; just print the error and keep trying.
                print(f"ERROR: watcher failed: {e}")

            # Sleep for a short time before checking again.
            time.sleep(max(1, int(args.poll_seconds)))

    # If we are NOT in watch mode, we run once and exit.
    csv_path = args.csv
    if csv_path is None:
        try:
            # If the user didn't provide --csv, pick the newest CSV in the folder.
            csv_path = _find_latest_worklist_csv(args.worklist_dir, args.prefix)
        except Exception as e:
            # If we cannot find a file, stop with a clear error.
            print(f"ERROR: {e}")
            return 2

    try:
        # Process the selected CSV file.
        process_csv(csv_path)
    except Exception as e:
        # If anything unexpected happens, print the error and exit with a failure code.
        print(f"ERROR: {e}")
        return 2

    # Success.
    return 0


if __name__ == "__main__":
    # This means: "only run main() when this file is run directly (not when imported by another file)".
    raise SystemExit(main())
