# 1,000 custom notices in about a minute

The standalone Rust pipeline created **1,000 personalized notices in about 60 seconds**: 2,000 pages, 1,000 separate password-protected copies and 10 grouped PDFs, each with a CSV listing page membership. The notices included different client information and 667 QR codes.

The interactive visual has two ways to explore the work:

- **Spend the minute:** a picture made of proportional blocks. Numbered blocks follow the rough processing order, starting with the client list. Filling and laying out each notice gets the largest block; selecting any block explains its share. Protected copies appear separately because they are made alongside notice creation.
- **[Follow a notice](../assets/notice-timing.html#journey):** a paper-and-copy walkthrough from the client list to the grouped PDF. Step through it, then replay the recorded output counts for the batch.

[Open the interactive visual](../assets/notice-timing.html) or its [static version](../assets/notice-timing.svg). Both use an approximate 60-second total. Choose Automatic, Light or Dark for the appearance. Automatic follows the documentation theme, or your system preference when opened separately. The replay starts paused.

<iframe src="../../assets/notice-timing.html" title="Where the minute goes: a time budget and notice walkthrough" width="100%" height="1450" loading="lazy" style="border:0;border-radius:12px"></iframe>

## What the timing includes

The whole-command measurement includes reading and preparing the input, creating and checking the notices, saving originals, making and checking protected copies, combining notices, and saving the run report. It uses one warm Typst engine, one encryption worker and four workers for combining independent groups. The application needs neither Python nor a separate Typst command.

This was fictional client data in a shared environment limited to 4 CPUs and 8 GiB RAM, with warm filesystem caches. It is a measured example, not a capacity guarantee. Your templates, page counts, fonts, settings and computer will affect the result. Your project supplies the wording and appearance; the upstream system assesses immunization status.

The blocks divide main-workflow time into a rounded minute. Their numbers show the rough order of the work. Steps 2–6 repeat for each person; file saving and report updates happen throughout. Encryption happens alongside notice creation and is not added to those blocks. The walkthrough explains the steps without assigning a measured time to an individual notice. Its replay uses recorded output completions.

## See a real command

![CLI demonstration creating notices for six fictional clients and showing live progress and the completion summary.](../assets/notice-demo.gif)

This short CLI demonstration uses the six fictional clients from ImmuKnow Template. It demonstrates the command and saved results; it is separate from the 1,000-client benchmark. See [getting started](getting_started.md) to run your own project.

Developers can follow the [library map](../developer_guide/architecture.md#libraries-in-the-pipeline) or the [visual maintenance notes](../developer_guide/documentation.md#maintaining-the-visuals).
