import streamlit as st
from typing import List
from app import (
    retrieve_company_documents,
    upload_and_get_doc_id,
    HybridSearch,
    download_sec_10k,
    download_web_annual_report
)
import pandas as pd
import os

st.set_page_config(page_title="SWOT Analysis", layout="wide")
st.title("📊 SWOT Analysis")

# --- Inputs ---
company_name = st.text_input("Enter Company Name:", "")

# Initialize session state for doc_ids
if "doc_ids" not in st.session_state:
    st.session_state.doc_ids = []

if st.session_state.doc_ids:
    st.markdown(f"### 📄 {company_name.capitalize()} Document IDs:")
    for doc_id in st.session_state.doc_ids:
        st.write(f"- {doc_id}")


if st.button("🔍 Begin Processing"):
    if not company_name:
        st.warning("Please enter a company name.")
    else:
        with st.spinner("Checking for documents..."):
            doc_ids = retrieve_company_documents(company_name)
            if doc_ids:
                st.session_state.doc_ids = doc_ids  # Save retrieved IDs
                if st.session_state.doc_ids:
                    st.markdown(f"### 📄 {company_name.capitalize()} Document IDs:")
                    for doc_id in st.session_state.doc_ids:
                        st.write(f"- {doc_id}")
                st.success("Proceed to Next Step (Analysis)")
            else:
                st.warning("No existing documents found. Trying to download new ones...")

                sec_path = download_sec_10k(company_name)
                web_path = download_web_annual_report(company_name)

                uploaded_ids = []

                if sec_path:
                    doc_id = upload_and_get_doc_id(sec_path)
                    if doc_id:
                        uploaded_ids.append(doc_id)
                        st.success(f"SEC 10-K uploaded with doc_id: {doc_id}")

                if web_path:
                    doc_id = upload_and_get_doc_id(web_path)
                    if doc_id:
                        uploaded_ids.append(doc_id)
                        st.success(f"Web Annual Report uploaded with doc_id: {doc_id}")

                if uploaded_ids:
                    st.session_state.doc_ids = uploaded_ids
                    st.write("✅ Uploaded document IDs:", uploaded_ids)
                    st.success("Proceed to Next Step (Analysis)")
                else:
                    st.error("❌ Could not download or upload any documents.")

# --- Query Section ---
st.divider()
st.subheader("📁 Generate Analysis based on Categories")

@st.cache_data
def load_prompts():
    return pd.read_excel("prompts.xlsx")

categories = [
    "Company Overview",
    "Strengths (Internal Positive Factors)",
    "Weaknesses (Internal Negative Factors)",
    "Opportunities (External Positive Factors)",
    "Threats (External Negative Factors)",
    "Additional Questions",
    "ALL"
]

selected_categories = st.multiselect("Select categories to query:", categories)

search_option = st.radio("Search Type", ("Documents Only", "Web Only", "Hybrid"), key="cat_search_option")

prompt_df = load_prompts()

if "ALL" in selected_categories:
    filtered_prompts = prompt_df
else:
    filtered_prompts = prompt_df[prompt_df['category'].isin(selected_categories)]

if st.button("🧠 Run Analysis"):
    if not company_name:
        st.warning("Please enter a company name.")
    elif filtered_prompts.empty:
        st.warning("No prompts found for the selected categories.")
    elif not st.session_state.get("doc_ids"):
        st.warning("Please retrieve or upload documents first.")
    else:
        with st.spinner("Running queries..."):
            search = HybridSearch()
            doc_ids = st.session_state.doc_ids
            os.makedirs("companies",exist_ok=True)
            os.makedirs(f"companies/{company_name}", exist_ok=True)

            for category in filtered_prompts['category'].unique():
                st.subheader(f"📂 {category}")
                cat_prompts = filtered_prompts[filtered_prompts['category'] == category]

                results = []

                for _, row in cat_prompts.iterrows():
                    prompt = row['prompts']

                    # Perform the search
                    if search_option == "Documents Only":
                        response = search.query_documents(prompt, doc_ids)
                        search_type = "Documents Only"
                    elif search_option == "Web Only":
                        response = search.query_web(prompt + f" for {company_name}")
                        search_type = "Web Only"
                    else:
                        response = search.hybrid_search(prompt, prompt+f" for {company_name}", doc_ids)
                        search_type = "Hybrid"

                    # Extract only the content from response
                    if isinstance(response, dict):
                        answer = response.get("content", "No response returned.")
                    else:
                        answer = response or "No response returned."

                    # Show in UI
                    st.markdown(f"**Question:** {prompt}")
                    st.markdown(f"**Answer:** \n {answer}")
            
                    st.markdown("---")

                    # Store result for saving
                    results.append({
                        "Prompt": prompt,
                        "Response": answer,
                        "Search Type": search_type
                    })

                # Save results to DataFrame and Excel
                df_results = pd.DataFrame(results)
                st.markdown(f"**Responses table for '{category}':**")
                st.dataframe(df_results)

                safe_category = category.replace(" ", "_").replace("(", "").replace(")", "")
                output_path = f"companies/{company_name}/{company_name}_{safe_category}.xlsx".replace(" ", "_")
                df_results.to_excel(output_path, index=False)

                # Download button
                if os.path.exists(output_path):
                    with open(output_path, "rb") as f:
                        st.download_button(
                            label=f"📥 Download '{category}' Responses as Excel",
                            data=f,
                            file_name=f"{safe_category}.xlsx",
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
