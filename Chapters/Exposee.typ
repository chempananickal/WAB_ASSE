#let exposee_content = [
  = Introduction

  Python @python is one of the most popular programming languages in the world @python_popularity, with a vast ecosystem of third-party packages available through the @pypi @pypicite. As the use of Python continues to grow, and especially as the frequency of commits to these packages by @llm:both:pl increases, understanding the quality and maintainability of these packages becomes increasingly important for developers and organizations that rely on them.

  @cyclomatic_complexity:cap is a graph theory based approach to compute the number of independent paths through a function @mccabe_1976. This gives a rough estimate of how many separate test cases one might need to cover every output of that function. A function with a higher @cyclomatic_complexity is traditionally less desirable, as it would theoretically have a larger number of edge cases wherein a potential bug could hide.

  = Objectives

  The objective of this paper is to analyze the relationship between @cyclomatic_complexity and bug-introducing commits in Python packages on @pypi, using the @szz @szzcite algorithm to identify bug-introducing commits. By mining a representative sample of popular Python packages, the aim is to understand whether higher complexity functions are more likely to be associated with bugs, and how this relationship has evolved over time.

  = Background and Related Work

  Previous research has explored the relationship between code complexity and software defects in various programming languages @bachmann_2010 @hassan_2009 @nagappan_ball_2005, but there is a lack of comprehensive studies focused specifically on Python packages in the @pypi ecosystem. Additionally, while the @szz algorithm has been widely used to identify bug-introducing commits, its application in the context of Python packages and its relationship with @cyclomatic_complexity does not appear to have been thoroughly investigated yet.
  = Research Questions

  The paper will seek to answer the following research questions:
  1. Can a meaningful correlation be observed between @cyclomatic_complexity and bug-proneness in Python packages on @pypi?
  2. How do bug-fixing commits affect the @cyclomatic_complexity of functions? Do they tend to increase, decrease, or stay the same?

  = Methodology
  The representative dataset will be the most depended upon Python packages on @pypi. This ranking will be extracted from Libraries.io, a platform by Sonar that tracks dependencies and usage across various package ecosystems @libraries_io. Starting from the top of this ranking, packages will be considered in order until ten packages with resolvable GitHub source repositories could be identified. For each selected package, release metadata and repository information will then be verified against the corresponding PyPI project metadata @pypicite. Afterwards, the repositories of the selected packages will be mined for data analysis @mining_github.

  For each package, bug fixing commits will be found by searching within commit messages that allude to fixing a bug. The @szz algorithm will then be applied to identify the bug-introducing commits that led to these fixes. For each function within the codebase which had at least one bug fix, the @cyclomatic_complexity will be computed at each commit where it was modified. The change in @cyclomatic_complexity across bug-fixing commits will then be tracked and analyzed.

  #pagebreak()
  = Planned Structure

  The paper will likely be structured as follows:

  - Introduction
  - Background and Related Work
  - Methodology
  - Results
  - Discussion
  - Conclusion and Future Work
  - References
  - AI Declaration
  - Declaration of Authorship
]
