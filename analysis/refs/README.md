# References — verification records

Each reference used in `report/report.md` has a raw record in this folder, fetched on 2026-10-24 with `curl`:
- Crossref API: `https://api.crossref.org/works/<DOI>`
- other sources: the publisher's or host's own page

No reference appears in the report without a record here.

| # | reference | DOI / URL | record | verified fields |
|---|---|---|---|---|
| 1 | Y. Hu, Y. Koren, C. Volinsky, "Collaborative Filtering for Implicit Feedback Datasets," *2008 Eighth IEEE Int. Conf. on Data Mining (ICDM)*, pp. 263–272, Dec. 2008 | 10.1109/ICDM.2008.22 | `crossref_10_1109_ICDM_2008_22.json` | authors, title, container, date, pages |
| 2 | T. H. Haveliwala, "Topic-sensitive PageRank," *Proc. 11th Int. Conf. on World Wide Web (WWW)*, pp. 517–526, May 2002 | 10.1145/511446.511513 | `crossref_10_1145_511446_511513.json` | authors, title, container, date, pages |
| 3 | P. Lops, M. de Gemmis, G. Semeraro, "Content-based Recommender Systems: State of the Art and Trends," in *Recommender Systems Handbook*, Springer, 2011, pp. 73–105 | 10.1007/978-0-387-85820-3_3 | `crossref_10_1007_978-0-387-85820-3_3.json` | authors, title, container, year, pages |
| 4 | A. Gulin, I. Kuralenok, D. Pavlov, "Winning The Transfer Learning Track of Yahoo!'s Learning To Rank Challenge with YetiRank," *Proc. Learning to Rank Challenge*, PMLR vol. 14, pp. 63–76, 2011 | https://proceedings.mlr.press/v14/gulin11a.html | `mlr_v14_gulin11a.html` (citation_* meta tags) | authors, title, proceedings, pages, publication date 2011/01/26 |
| 5 | P. Cremonesi, Y. Koren, R. Turrin, "Performance of recommender algorithms on top-N recommendation tasks," *Proc. 4th ACM Conf. on Recommender Systems (RecSys)*, pp. 39–46, Sep. 2010 | 10.1145/1864708.1864721 | `crossref_10_1145_1864708_1864721.json` | authors, title, container, date, pages |
| 6 | Kaggle, "sweet.tv - TV program recommender," competition page | https://www.kaggle.com/competitions/sweettv-tv-program-recommender | `kaggle_competition_page.html` (HTTP 200) | page title, description ("Create the algorithm that predicts user's TV program preferences") |

The Kaggle page is rendered with JavaScript, so the saved HTML holds only the title and description meta tags. The rules text (80% rule, MAP@5) could not be verified from the saved record. The report takes those rules from the exam brief, not from this record.
