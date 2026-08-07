"""Real-sample check: pull recent surgery-MeSH articles and see what fraction
we can get full text for via Europe PMC / Unpaywall vs abstract-only."""
from config import SURGERY_MESH_QUERY
from fulltext import get_full_text
from pubmed_client import efetch_articles, esearch_pmids

SAMPLE_SIZE = 20


def main():
    pmids = esearch_pmids(SURGERY_MESH_QUERY, retmax=SAMPLE_SIZE)
    articles = efetch_articles(pmids)
    print(f"esearch matched sample of {len(articles)} articles\n")

    counts = {"pmc_oa": 0, "europepmc": 0, "unpaywall": 0, "none": 0}
    for a in articles:
        text, source = get_full_text(pmcid=a["pmcid"], doi=a["doi"])
        source = source or "none"
        counts[source] += 1
        length = len(text) if text else 0
        print(
            f"PMID {a['pmid']:>9}  pmcid={a['pmcid'] or '-':>12}  "
            f"doi={'yes' if a['doi'] else 'no ':>3}  -> {source:<10} ({length} chars)  "
            f"{a['title'][:60]}"
        )

    total = len(articles)
    found = counts["pmc_oa"] + counts["europepmc"] + counts["unpaywall"]
    print(f"\nfull text coverage: {found}/{total} "
          f"(pmc_oa={counts['pmc_oa']}, europepmc={counts['europepmc']}, "
          f"unpaywall={counts['unpaywall']}, none={counts['none']})")


if __name__ == "__main__":
    main()
