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
)
