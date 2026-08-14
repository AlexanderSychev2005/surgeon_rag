# Источники для диплома — surgeon_rag

Собрано по темам, которые нужны для соответствующих разделов диплома. PDF — там, где
удалось скачать открытую версию; для остального (paywall / веб-страницы без PDF) —
просто ссылка.

## 01. MedCPT — энкодер, который используем

Для раздела про архитектуру ретривала (bi-encoder + cross-encoder), математику contrastive
learning.

- **[PDF]** `Shi_2023_MedCPT_arXiv.pdf` — препринт, arXiv: https://arxiv.org/abs/2307.00589
- **[PDF]** `Shi_2023_MedCPT_Bioinformatics_OxfordAcademic.pdf` — рецензированная версия
  (Bioinformatics / Oxford Academic): https://academic.oup.com/bioinformatics/article/39/11/btad651/7335842

## 02. RAG в медицине — обзоры (для "related work")

- **[PDF]** `Systematic_Review_RAG_Techniques_Metrics_Challenges_2025.pdf` —
  A Systematic Literature Review of RAG: Techniques, Metrics, and Challenges (2025):
  https://arxiv.org/pdf/2508.06401
- **[PDF]** `RAG_in_Healthcare_Comprehensive_Review_2025.pdf`: https://www.preprints.org/manuscript/202508.1022
- **[PDF]** `JMIR_RAG_Medical_Nursing_Scoping_Review_2025.pdf` — Improving LLM
  Applications in Medical/Nursing Domains with RAG: Scoping Review (JMIR, 2025):
  https://www.jmir.org/2025/1/e80557
- **[ссылка]** RAG in medicine: scoping review of technical implementations, clinical
  applications, ethics (ScienceDirect, paywall): https://www.sciencedirect.com/science/article/pii/S2666379126003447

## 03. RAG именно над PubMed-литературой (близкие проекты)

- **[PDF]** `Biomedical_Literature_QA_RAG_System_2025.pdf`: https://arxiv.org/abs/2509.05505
- **[PDF]** `RAG-BioQA_Long_Form_Biomedical_QA.pdf`: https://arxiv.org/html/2510.01612
- **[PDF]** `AlzheimerRAG_Multimodal_RAG_PubMed.pdf` — Multimodal RAG for Clinical Use
  Cases using PubMed articles: https://arxiv.org/pdf/2412.16701

## 04. Bi-encoder + cross-encoder архитектура

Для раздела про математику ретривала/reranking (cosine similarity, cross-attention scoring).

- **[PDF]** `Survey_Model_Architectures_Information_Retrieval_2025.pdf`: https://arxiv.org/html/2502.14822v2
- **[PDF]** `In_Defense_of_CrossEncoders_ZeroShot_Retrieval.pdf`: https://arxiv.org/pdf/2212.06121
- **[PDF]** `Ensembling_CrossEncoders_GPT_Rerankers_BiomedicalQA.pdf`: https://arxiv.org/pdf/2507.05577

## 05. Выбор векторной БД (обоснование Qdrant)

Только веб-страницы, PDF-версий не существует — просто ссылки.

- Qdrant vs Pinecone (официальное сравнение от Qdrant): https://qdrant.tech/blog/comparing-qdrant-vs-pinecone-vector-databases/
- Pinecone vs Qdrant vs Weaviate (независимое сравнение, Xenoss): https://xenoss.io/blog/vector-database-comparison-pinecone-qdrant-weaviate

## 06. Препринты и рецензирование (обоснование republish-check логики)

- **[PDF]** `Tracking_Changes_Preprint_to_Publication_Pandemic.pdf` — Preprints in motion:
  tracking changes between preprint posting and journal publication during a pandemic:
  https://www.ncbi.nlm.nih.gov/pmc/articles/PMC8806067/
- **[PDF]** `PreprintToPaper_Dataset_bioRxiv_Journal_Linking.pdf`: https://arxiv.org/pdf/2510.01783
- **[ссылка]** bioRxiv/medRxiv FAQ (официальное подтверждение "no peer review at
  posting", не статья, просто справка): https://www.biorxiv.org/about/FAQ
