#let results_content = [
  = Results

  == Dataset Overview

  The final dataset contains 47,151 analyzed functions across ten repositories. Of these functions, 12,882 were touched by at least one bug-fixing commit. Summed over the selected repositories, the mining pass identified 9,034 bug-fix commits and 15,442 unique bug-introducing commits attributed by the simplified @szz stage. The selected repositories vary substantially in size. At the low end, pytest-cov contributes 52 analyzed functions, while scipy contributes 13,603 (see @dataset-overview-table).

  #let overview_rows = csv("../Code/output/latest/selected_package_overview.csv", row-type: dictionary)
  #let overview_cells = (
    overview_rows
      .map(row => (
        [#row.at("rank")],
        [#row.at("package")],
        [#row.at("version")],
        [#row.at("functions_analyzed")],
      ))
      .flatten()
  )

  #figure(
    table(
      columns: 4,
      inset: 6pt,
      align: (right, left, left, right),
      table.header([*Rank*], [*Package*], [*Version*], [*Functions analyzed*]),
      ..overview_cells,
    ),
    caption: [Packages with their reverse dependency rank, version, and number of analyzed functions.],
  ) <dataset-overview-table>

  == Complexity and Bug-fix Correlation

  To estimate the overall relationship between function complexity and bug-fix activity, two correlation coefficients were computed at the package level.
  The Pearson coefficient measures the strength of the linear relationship between two variables, ranging from -1 (perfect negative linear relationship) to +1 (perfect positive linear relationship), with 0 indicating no linear association @pearson. The Spearman coefficient is a rank-based alternative that captures monotonic relationships more broadly, without assuming linearity or a particular distribution of the data @spearman.

  Both are reported here because complexity distributions in real codebases tend to be heavily right-skewed, which makes the rank-based Spearman measure a more robust primary indicator. Both measures are consistently weakly positive across all ten repositories, indicating that higher complexity functions tend to be associated with more bug-fix commits.

  The strongest Spearman correlation appears in black ($r_s = 0.429$), followed by pytest ($r_s = 0.319$) and pytest-cov ($r_s = 0.296$), while the weakest is pydantic ($r_s = 0.134$). The Pearson correlation coefficients show a similar pattern (see @correlation-table).

  #let correlation_rows = csv("../Code/output/latest/package_correlation_table.csv", row-type: dictionary)

  #let correlation_cells = (
    correlation_rows
      .map(row => (
        [#row.at("package")],
        [#row.at("spearman_r")],
        [#row.at("pearson_r")],
      ))
      .flatten()
  )

  #figure(
    table(
      columns: 3,
      inset: 6pt,
      align: (left, right, right),
      table.header([*Package*], [*Spearman $r_s$*], [*Pearson $r$*]),
      ..correlation_cells,
    ),
    caption: [Correlation coefficients between function complexity and bug-fix commit frequency for the ten analyzed packages.],
  ) <correlation-table>

  Taken together, these results seem to provide an answer to the first research question: higher function complexity is consistently associated with more bug-fix activity, although the strength of that association differs considerably across projects.

  == Maintenance Concentration

  The bucketed view sharpens this pattern. Most analyzed functions fall into the 1--20 complexity bucket, and only 26.5% of them were touched by at least one bug-fix commit. In the 21--40 bucket, that share rises to 54.6%. The 41--60 and 61--80 buckets remain above 52%, and the smaller high-complexity buckets are mostly similar or higher, although those ranges contain far fewer functions. The mean number of bug-fix commits per function follows the same pattern, rising from 0.48 in the 1--20 bucket to 1.76 in the 21--40 bucket and 2.16 in the 41--60 bucket.

  #figure(
    image("../Code/output/latest/plots/complexity_bucket_bugfix_share.png", width: 100%),
    caption: [Bug-fix share by complexity bucket. Functions above a complexity of 20 show substantially higher bug-fix shares than the largest low-complexity bucket.],
  ) <bucket-fig>

  The cumulative concentration plot answers a slightly different question. It orders all functions from highest complexity to lowest complexity, then shows how much of the total bug-fix activity has been accumulated after taking the top $x$% of that ordering. If bug-fix activity were spread evenly across the codebase, the curve would follow the diagonal. Instead, it stays above the diagonal throughout. The 1% most complex functions account for 3.8% of all bug-fix commits, the top 5% account for 16.7%, the top 10% account for 29.1%, the top 20% account for 47.3%, and the top half account for 73.8%. This means maintenance work is meaningfully concentrated in more complex functions, but not so strongly that a very small minority of functions accounts for nearly all fixes.

  #figure(
    image("../Code/output/latest/plots/hotspot_concentration.png", width: 100%),
    caption: [Cumulative concentration of bug-fix activity among the most complex functions.],
  ) <hotspot-fig>

  The repeat-fix distribution highlights the same concentration from another angle. 72.7% of analyzed functions were not touched by any bug-fix commit, 16.3% were touched once, and 5.7% were touched twice. After that, the distribution decays into a long tail, with a small number of functions accumulating many repeated bug-fix touches and the highest observed value reaching 29. Together, the bucketed, cumulative, and repeat-fix views all point to the same result: higher complexity is associated not only with a greater chance of being fixed at least once, but also with a greater share of the ongoing maintenance burden.

  == Complexity Changes in Bug-fixing Commits

  The bug-fix event summary shows that most bug-fixing touches do not substantially alter function complexity. Of all bug-fix events, 62.0% fall into the "No change" category. Complexity increases account for 13.0%, decreases for 5.5%, newly introduced functions for 13.3%, and deleted or renamed functions for 6.1%. In other words, the most common outcome of a bug-fixing commit is not simplification but local repair inside an existing function.

  #figure(
    image("../Code/output/latest/plots/bugfix_complexity_changes.png", width: 100%),
    caption: [Complexity-change categories observed at bug-fixing commits. No-change outcomes dominate, and increases are more common than decreases.],
  ) <bugfix-change-fig>

  This distribution suggests that complexity is related more strongly to where bug-fix activity occurs than to a general tendency for fixes to simplify code. When complexity does change, increases are more common than decreases, which indicates that fixes often add guards, branches, or special-case handling rather than removing structural decision points. Many fixes therefore appear to adjust behavior inside already complex functions without materially reducing their measured complexity.

  == SZZ Attributions

  The @szz results tell a similar but more qualified story. Across all attributed rows, "No change" remains the largest category at 39.7%, followed by "Function pair not recoverable" at 24.5% and "New function" at 17.9%. Complexity increases account for 12.4% of all @szz attributions, while decreases account for 5.3% (see @szz-change-fig). The large unrecoverable share is important because it reflects the difficulty of matching historical function pairs conservatively across real repository histories.

  #pdf.attach(
    "../Code/output/latest/szz_summary.csv",
    relationship: "source",
    description: "SZZ attribution raw data generated by the code",
  ) <szz-data>

  #figure(
    image("../Code/output/latest/plots/szz_complexity_changes.png", width: 100%),
    caption: [Complexity-change categories for simplified SZZ attributions. A substantial share of attributions cannot be recovered at function level, but matched rows still show more increases than decreases.],
  ) <szz-change-fig>

  When only matched attributions are considered, the pattern becomes clearer: 69.1% of matched @szz rows show no change, 21.7% show an increase, and 9.2% show a decrease. Thus, among attributable function pairs, increases are distinctly more common than decreases, but unchanged functions still dominate. This suggests that bug-introducing commits are more likely to add complexity than remove it, although a rise in cyclomatic complexity is neither necessary nor sufficient for a later defect.

  #pdf.attach(
    "../Code/output/latest/matched_szz_summary.csv",
    relationship: "source",
    description: "SZZ attributions, but filtered for only the matched function pairs.",
  ) <szz-matched-data>

  The temporal distance between attributed bug-introducing and bug-fixing commits is also substantial. Across 27,526 unique attributed commit pairs with valid, non-negative timestamps, the median lag is 751.1 days, with an interquartile range from 189.0 to 1807.8 days. The package-level summaries show substantial variation. Pydantic has the shortest median lag at 133.1 days, while pytest-cov reaches 2332.5 days, requests 1888.4 days, and scipy 1232.6 days. Many attributed bugs therefore remain latent for months or years before being repaired.

  #figure(
    image("../Code/output/latest/plots/szz_fix_lag_distribution.png", width: 100%),
    caption: [Distribution of time lags between attributed bug-introducing commits and their corresponding fixes.],
  ) <szz-lag-fig>

  Taken together, these findings answer the second research question in a qualified way. Bug-fixing commits usually leave measured complexity unchanged, and when complexity does change, increases are more common than decreases. The simplified @szz results point in the same direction for attributed bug-introducing commits, but they also show that a substantial fraction of historical function pairs cannot be recovered confidently. The overall picture is therefore not one of direct causation, but of elevated maintenance risk: higher complexity is associated with more bug-fix activity and a larger share of repeated maintenance, while the actual path from change to defect remains shaped by package-specific workflows and long time lags.

]
