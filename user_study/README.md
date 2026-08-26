# docval user study

A small Streamlit app that lets a participant download a document with
known structural faults (`Sample Documents/Word/Assignment_v1.docx`,
offered under the neutral name `assignment_template.docx`), fix it, upload
it back, see the same report `docval.py` would produce, answer the UEQ-S,
and have both logged as one readable row in a Google Sheet.

It reuses `word_extractor.py` and `rules.py` from the main project
unchanged - `app.py` only arranges the study around them.

## What you need to do before this can go live

Everything below is external setup - accounts, permissions, and the
Streamlit deployment itself - that only you can do; none of it is code.

### 1. Create the Google Sheet

1. Create a new Google Sheet. Its first row will be filled in
   automatically by the app the first time it runs - leave it empty.
2. Copy its URL; you will paste it into secrets in step 3.

### 2. Create a Google Cloud service account

The app writes to the sheet as a "robot" account, not as you, so it needs
its own credentials.

1. In the [Google Cloud Console](https://console.cloud.google.com/), create
   a project (or use an existing one).
2. Enable the **Google Sheets API** for that project (APIs & Services →
   Enable APIs and Services → search "Google Sheets API" → Enable).
3. Create a service account (APIs & Services → Credentials → Create
   Credentials → Service account). Any name is fine.
4. Open the service account, go to **Keys → Add key → Create new key →
   JSON**. This downloads a `.json` file - keep it private, it is a
   credential.
5. Open the Google Sheet from step 1, click **Share**, and share it with
   the service account's email address (it looks like
   `something@your-project.iam.gserviceaccount.com`, found inside the JSON
   file as `client_email`) with **Editor** access.

### 3. Fill in the app's secrets

Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` in this
folder, and fill it in from the JSON file you downloaded: each field in the
`[gcp_service_account]` section has a matching key in the JSON (`type`,
`project_id`, `private_key`, `client_email`, ...). Put the Sheet's URL from
step 1 under `[sheet] url`.

`secrets.toml` is already in `.gitignore` - **never commit it**, since it
contains a private key. Test locally first:

```bash
cd user_study
pip install -r requirements.txt
streamlit run app.py
```

Upload any `.docx` and confirm a row appears in the Google Sheet.

### 4. Deploy on Streamlit Community Cloud (free)

1. Push this repository to GitHub (a public repo is fine; a private repo
   also works on the free tier).
2. Go to [share.streamlit.io](https://share.streamlit.io), sign in with
   GitHub, and click "New app".
3. Point it at this repository, branch `develop` (or wherever this lives),
   and set the main file path to `user_study/app.py`.
4. Before or after the first deploy, open the app's **Settings → Secrets**
   and paste the entire contents of your local `secrets.toml` there. This
   is the deployed equivalent of the local file - the app reads
   `st.secrets` the same way in both places.
5. Streamlit gives you a public URL (`your-app-name.streamlit.app`) - that
   is what you send to participants.

### 5. Before real participants use it

- **Replace the placeholder text** near the top of `app.py` (marked
  `PLACEHOLDER`) with your actual study introduction and consent text. What
  is there now is instructional filler, not consent language, and must not
  be used as such.
- Consider whether you want the `Participant ID` field, and whether
  participants should be told what it is for.
- Try the whole flow yourself end to end at least once against the
  deployed URL, not just locally - Streamlit Cloud's environment can behave
  slightly differently (e.g. package versions) from your machine.

## What gets logged

One row per submission, with a plain-language header naming every column:
the time, the optional Participant ID, the file name, the result ("Passed"
or "N issue(s)"), the total issue count, one column per check spelled out
by name ("Heading structure", "Table of contents linked", ...), the eight
raw UEQ-S answers (each 1-7, headed by the word pair itself, e.g.
"Obstructive - Supportive"), and finally the two scores computed from
them - **Pragmatic Quality** and **Hedonic Quality**, each already averaged
to one number so you do not need a spreadsheet formula to read the result.

The header is checked on every submission, not just written once: if row 1
of the sheet is ever not exactly the expected header - for instance
because you tested the app against a sheet that already had stray rows in
it - the correct header is inserted above whatever is there, so every row
from that point on is readable. If your sheet currently has unlabeled rows
from earlier testing, the simplest fix is to clear them out once by hand;
new submissions will always come in under a proper header.

The uploaded document itself is **not** stored anywhere - only the report
generated from it.

## About the survey

The [UEQ-S](https://www.ueq-online.org) (User Experience Questionnaire,
Short Version), the eight official item pairs in their official order and
wording. Each is a single click on a 1-7 row - no separate instructions
needed per item, just the one line shown once at the top of the section.
Free to use for research; citing Schrepp, Hinderks & Thomaschewski (2017)
is appreciated.

The first four items score **Pragmatic Quality** (can the tool be used
effectively); the last four score **Hedonic Quality** (was using it a good
experience). Both are computed automatically and written to the sheet
alongside the eight raw answers.

Two things worth knowing if you write this up formally:

- The official instrument sometimes puts the positive word on the *left*
  instead of the right, per item, to reduce the tendency to rate everything
  on the same side. This app always puts it on the right, which is simpler
  to build and to answer, at the cost of that safeguard.
- The six named UEQ scales (Attractiveness, Perspicuity, Efficiency,
  Dependability, Stimulation, Novelty) are **not** available from UEQ-S -
  they require the full 26-item UEQ. UEQ-S only gives the two combined
  scores above.

Item wording and grouping live in `UEQ_ITEMS` near the top of `app.py`.
