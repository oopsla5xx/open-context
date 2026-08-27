# Analytics Pipeline — Agent Notes

This repo is a small internal analytics pipeline: a bag of standalone
Python scripts run on a schedule, not a web app. There is no
controller/model/view layering — each script owns its input, its
transform, and its output end to end.

## Rules

- Never use production database credentials in a script committed to
  this repo. All scripts read `DATABASE_URL` from the environment;
  local development uses a `.env.local` file that is gitignored.
- Every report script must cache its intermediate aggregation result to
  `cache/<report_name>.parquet` before writing the final export. Reports
  are re-run manually when someone disputes a number, and re-aggregating
  from raw rows every time is both slow and a source of nondeterminism
  if upstream data changed underneath a re-run.
