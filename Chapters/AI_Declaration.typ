#let ai_declaration_intro = [
  The usage of AI tools within this project is documented here. I declare that I have documented all interactions with AI tools, including the prompts used and the outputs received.
]

#let ai_declaration_entries = (
  (
    system: [GitHub Copilot 1],
    prompt: [I want you to rewrite my template from LaTeX to Typst, and make it look like it did before.],
    usage: [Recreated the template in Typst, maintaining the original appearance.],
  ),
  (
    system: [GitHub Copilot 2],
    prompt: [In Code/, write a Python script that finds the top most depended-upon Python packages and analyzes the correlation between function cyclomatic complexity and bug-fix frequency over an adjustable time window, with plots and tables.],
    usage: [Created the analysis pipeline.],
  ),
  (
    system: [GitHub Copilot 3],
    prompt: [Use pip to install any required packages, not conda.],
    usage: [Added pip dependency setup.],
  ),
  (
    system: [GitHub Copilot 4],
    prompt: [Correct the package discovery so the ranking reflects dependency counts and the analysis uses real source repositories rather than release repositories.],
    usage: [Fixed discovery and repo resolution.],
  ),
  (
    system: [GitHub Copilot 5],
    prompt: [Make the analysis practical to run by adding adjustable bounds for the mined recent commit history.],
    usage: [Added bounded commit mining.],
  ),
  (
    system: [GitHub Copilot 6],
    prompt: [Use ProcessPoolExecutor to accelerate the script.],
    usage: [Parallelized package mining.],
  ),
  (
    system: [GitHub Copilot 7],
    prompt: [Add compact logging and terminal progress bars, show phases such as cloning, mining, SZZ, and plotting, and remove Typst table generation.],
    usage: [Added logs and progress bars; removed Typst exports.],
  ),
  (
    system: [GitHub Copilot 8],
    prompt: [Fix the parser warning noise produced while mining repositories.],
    usage: [Suppressed parser warnings.],
  ),
  (
    system: [GitHub Copilot 9],
    prompt: [Fix the Windows UnicodeDecodeError that occurs while reading subprocess output during mining.],
    usage: [Hardened subprocess decoding.],
  ),
  (
    system: [GitHub Copilot 10],
    prompt: [Implement flexible caching so repeated runs can reuse already mined information while still respecting parameter changes.],
    usage: [Added parameter-aware mining cache.],
  ),
  (
    system: [GitHub Copilot 11],
    prompt: [Add analysis support for native code too and update the progress bars more often.],
    usage: [Added mixed-language analysis; increased progress updates.],
  ),
  (
    system: [GitHub Copilot 12],
    prompt: [Use all languages recognized by lizard instead of restricting the non-Python analysis to C-family files.],
    usage: [Expanded lizard language coverage.],
  ),
  (
    system: [GitHub Copilot 13],
    prompt: [Add a CLI option to restrict the analysis to Python files only while keeping mixed-language analysis as the default.],
    usage: [Added Python-only analysis mode.],
  ),
  (
    system: [GitHub Copilot 14],
    prompt: [Refactor the analysis script into helper modules and keep the main script as the orchestration entrypoint.],
    usage: [Reorganized the analysis code into helper modules.],
  ),
  (
    system: [GitHub Copilot 15],
    prompt: [Replace the PyDriller repository mining implementation with direct Git CLI queries and keep the SZZ analysis working on top of that path.],
    usage: [Replaced PyDriller-based mining with Git CLI mining and SZZ integration.],
  ),
  (
    system: [GitHub Copilot 16],
    prompt: [Improve the SZZ output by separating unresolved cases and adding rename-aware matching for moved files and renamed functions.],
    usage: [Added SZZ attribution categories and rename-aware matching.],
  ),
  (
    system: [GitHub Copilot 17],
    prompt: [Rename the stale non-Python parser helper so it reflects the current lizard-based multi-language behavior.],
    usage: [Renamed the non-Python parser helper for clarity.],
  ),
  (
    system: [GitHub Copilot 18],
    prompt: [Add NumPy-style docstrings to the important analysis, mining, and reporting functions.],
    usage: [Added NumPy-style docstrings to key functions.],
  ),
  (
    system: [GitHub Copilot 19],
    prompt: [Rewrite the repository README so it reads like a cohesive project README rather than patchwork.],
    usage: [Reworked the README structure and usage documentation.],
  ),
  (
    system: [GitHub Copilot 20],
    prompt: [Make plotting reusable from precomputed results, add richer reporting outputs, and export grouped raw JSON.],
    usage: [Added plot-only rendering, extra summaries and plots, and raw JSON output.],
  ),
  (
    system: [GitHub Copilot 21],
    prompt: [Persist commit dates for bug-fixing and bug-introducing commits and add a time-series plot for bug-fix commits.],
    usage: [Added commit-date export and bug-fix timeline reporting.],
  ),
  (
    system: [GitHub Copilot 22],
    prompt: [Replace the many CLI flags with a TOML config file, keep only --cfg in the CLI, and make rename-matching thresholds configurable.],
    usage: [Introduced TOML-based configuration and configurable rename matching.],
  ),
  (
    system: [GitHub Copilot 23],
    prompt: [Add config validation, timeline granularity options, and clearer config comments.],
    usage: [Added stricter config validation and documented config options.],
  ),
  (
    system: [GitHub Copilot 24],
    prompt: [Replace the less useful plot, improve the reporting plots, and make the bucket ranges clearer.],
    usage: [Reworked plots and simplified the complexity buckets.],
  ),
  (
    system: [GitHub Copilot 25],
    prompt: [Preserve full commit messages in raw JSON and regenerate compact CSV messages from that source.],
    usage: [Made raw JSON the source of truth for compact message exports.],
  ),
  (
    system: [GitHub Copilot 26],
    prompt: [Exclude documentation files from the complexity and SZZ analysis.],
    usage: [Excluded documentation files from analysis inputs.],
  ),
)
