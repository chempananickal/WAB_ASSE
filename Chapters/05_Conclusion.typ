#let conclusion_content = [
  = Conclusion

  #quote(
    "Correlation does not imply causation",
    block: true,
    attribution: [F.A.D (Pseudonymous Author)#cite(<correlation_not_causation>)],
  )

  This study examined whether cyclomatic complexity is associated with bug-proneness in a sample of important Python packages and how bug-fixing activity relates to complexity change. The answer to the first research question is yes, but only in a qualified sense. Across all ten analyzed repositories, both Pearson and Spearman correlations between function complexity and bug-fix activity are positive, and the concentration analyses show that more complex functions carry a disproportionate share of maintenance. The top 10% most complex functions account for 29.1% of bug-fix commits, and the top 20% account for 47.3%. Complexity is therefore a useful indicator of elevated maintenance risk.

  The answer to the second research question is more nuanced. Most bug-fixing commits do not materially change measured complexity, and the same is true for most matched @szz attributions. When complexity does change, increases are more common than decreases. Bug fixes therefore do not usually simplify the affected code, and bug-introducing commits are more likely to add structural decision points than remove them. At the same time, the substantial share of unrecoverable @szz pairs and the long median lag between attributed introduction and later repair show that defects emerge through longer historical processes than a single complexity increase can explain.

  Overall, the findings support a pragmatic conclusion. Higher cyclomatic complexity is not a direct proof that a function is faulty, but it is a useful warning sign for where defects and repeated maintenance are more likely to accumulate. For maintainers of high-impact Python packages, complexity appears to be most valuable as a prioritization signal for review, testing, and refactoring, rather than as a causal diagnosis on its own.

  == Future Work

  There are a few notable avenues for future research.

  1. Replace the commit-message heuristic with issue-linked or classifier-based bug-fix identification.
  2. Extend the package sample beyond just the few most depended-upon projects to test how strongly the findings generalize.
  3. Compare @cyclomatic_complexity with additional complexity measures such as cognitive or change complexity.
  4. Use a more intelligent @szz tracing procedure that can recover more function pairs and better handle merges, renames, and refactorings.
]
