# 1,000 custom notices in about a minute

The standalone Rust pipeline created **1,000 personalized notices in about 60 seconds**: 2,000 pages, 1,000 separate password-protected copies and 10 grouped PDFs, each with a CSV listing page membership. The input repeated six fictional Template cases with unique client IDs,
English and French notices, and 667 QR codes.

| Main workflow activity | Included work | Share of a rounded minute |
| --- | --- | ---: |
| Create the notices | Typst layout, PDF export, cache cleanup | 41 seconds |
| Prepare, check and save | Input preparation, evidence/PDF checks, file writes and fingerprints | 10 seconds |
| Group the notices | Bundle assembly | 6 seconds |
| Write the report | Checkpoints and final reports | 3 seconds |

These are aggregate shares of the measured main workflow, rounded to total 60 seconds, rather than consecutive intervals. Creating, checking and saving repeat for each person, and report updates happen throughout. Creating notices includes page layout, QR codes, PDF export and cache cleanup. Protected copies are made concurrently and are not added to these shares. See the [processing diagram](../developer_guide/architecture.md) for the overlap.

## What the timing includes

The whole-command measurement includes reading and preparing the input, creating and checking the notices, saving originals, making and checking protected copies, combining notices, and saving the run report. It used one warm Typst engine, one encryption worker and four workers for combining independent groups.

This was fictional client data in a shared environment limited to 4 CPUs and 8 GiB RAM, with warm filesystem caches. It is a measured example, not a capacity guarantee. Your templates, page counts, fonts, settings and computer will affect the result. Your project supplies the wording and appearance; the upstream system assesses immunization status.

The uninstrumented command took 57.76 seconds; the profiled command took 58.74 seconds, including 58.22 seconds inside the workflow. The measurements used production commit `a5bfe974178731629810162f6b99f48f353cf5f8` and profiling commit `81ac287` on `experiment/workflow-profiling`. Instrumentation is not part of the production application. The [measurement data](../assets/notice-timings.json) retains the finer activity bins, output completion samples and input hash. See [testing](../developer_guide/testing.md#measure-the-complete-command) for measurement guidance.
