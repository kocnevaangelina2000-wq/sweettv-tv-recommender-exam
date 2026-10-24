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
| 6 | Kaggle, "sweet.tv - TV program recommender," competition page and Data tab | https://www.kaggle.com/competitions/sweettv-tv-program-recommender (accessed 2026-10-24) | `kaggle_competition_page.html` (HTTP 200); `kaggle_data_target_rule.png` and `kaggle_data_file_descriptions.png` (screenshots of the Data tab, saved by the author) | page: title and description. `kaggle_data_target_rule.png`: target rule (screen time ≥ 80%, top five programmes by count) and the 50/50 public/private split by users. `kaggle_data_file_descriptions.png`: the tab's "File descriptions" names (`dataset11-30week.csv`, `export_arh_10-19.csv`, `export_arh_20-30.csv`, `end_time`) next to the files actually served (trap B2) |
| 7 | LLM4Rec course (HSE University), lecture slides on ranking metrics, "MAP@K" | course material | none (not publicly archived) | normaliser min(K, \|relevant\|); the slide example (0.9167 / 0.5333) is reproduced in `tests/test_protocol.py` |

The saved Kaggle HTML holds only the title and description, because the page is rendered with JavaScript. The target rule, the top-5-by-count answer and the 50/50 split are therefore cited from the Data-tab screenshot `kaggle_data_target_rule.png`, not from the HTML. The file-name mismatch of trap B2 is cited from `kaggle_data_file_descriptions.png`. The MAP@5 normaliser min(5, |truth|) comes from the course slide [7], not from Kaggle. Reference 7 is the only one without a saved public record.
