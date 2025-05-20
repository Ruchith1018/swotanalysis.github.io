import requests
from googlesearch import search
import re
from urllib.parse import urlparse
from weasyprint import HTML
from typing import List, Dict, Any

# Configuration for SEC requests
SEC_HEADERS = {
    "User-Agent": "Your Name YourCompany yourname@yourcompany.com"  # Replace with your details
}

# Google search and download headers
DOWNLOAD_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept": "application/pdf",
    "Referer": "https://www.google.com"
}

# API base URL for the document database
API_BASE = "http://54.198.215.188:8000"

def normalize_company_name(name):
    return re.sub(r"[^a-zA-Z0-9]", "", name).lower()

def find_annual_report_pdf(company_name, max_results=20):
    query = f'"{company_name}" "annual report" filetype:pdf'
    print(f"Searching Google for: {query}")
    
    results = list(search(query, num_results=max_results))
    
    norm_name = normalize_company_name(company_name)

    scored_links = []
    for url in results:
        if not url.lower().endswith(".pdf"):
            continue
        score = 0

        if "annual" in url.lower():
            score += 2

        domain = urlparse(url).netloc
        if norm_name in normalize_company_name(domain):
            score += 3

        if "2024" in url or "fy2024" in url.lower():
            score += 1

        scored_links.append((score, url))

    if not scored_links:
        print("No PDF found.")
        return None

    scored_links.sort(reverse=True)
    best_url = scored_links[0][1]
    print(f"Selected PDF: {best_url}")
    return best_url

def download_pdf(url, company_name, report_type="Annual_Report"):
    try:
        response = requests.get(url, stream=True, headers=DOWNLOAD_HEADERS, timeout=15)
        response.raise_for_status()

        filename = f"{company_name.replace(' ', '_')}_{report_type}.pdf"
        with open(filename, "wb") as f:
            for chunk in response.iter_content(1024):
                f.write(chunk)
        print(f"Downloaded to: {filename}")
        return filename
    except Exception as e:
        print(f"Failed to download PDF: {e}")
        return None

def get_cik_from_name(name):
    url = "https://www.sec.gov/files/company_tickers.json"
    response = requests.get(url, headers=SEC_HEADERS)
    if not response.ok:
        print("Failed to get CIK list:", response.status_code)
        return None

    data = response.json()
    for entry in data.values():
        if name.lower() in entry["title"].lower():
            return str(entry["cik_str"]).zfill(10)
    return None

def get_latest_10k_url(cik):
    url = f"https://data.sec.gov/submissions/CIK{cik}.json"
    response = requests.get(url, headers=SEC_HEADERS)
    if not response.ok:
        print("Failed to get filings:", response.status_code)
        return None

    data = response.json()
    recent = data.get("filings", {}).get("recent", {})
    for i, form in enumerate(recent.get("form", [])):
        if form == "10-K":
            acc_num = recent["accessionNumber"][i].replace("-", "")
            doc = recent["primaryDocument"][i]
            return f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc_num}/{doc}"
    return None

def download_sec_10k(company_name):
    cik = get_cik_from_name(company_name)
    if not cik:
        print("Company not found in SEC database.")
        return None

    print("Found CIK:", cik)
    url = get_latest_10k_url(cik)
    if not url:
        print("10-K filing not found.")
        return None

    print("Downloading 10-K HTML:", url)
    response = requests.get(url, headers=SEC_HEADERS)
    if not response.ok:
        print("Download failed:", response.status_code)
        return None

    html_content = response.text
    pdf_filename = f"{company_name.replace(' ', '_')}_10-K.pdf"

    try:
        HTML(string=html_content, base_url=url).write_pdf(pdf_filename)
        print(f"Saved SEC 10-K PDF to: {pdf_filename}")
        return pdf_filename
    except Exception as e:
        print("PDF conversion failed:", str(e))
        return None

def download_web_annual_report(company_name):
    url = find_annual_report_pdf(company_name)
    if url:
        return download_pdf(url, company_name, "Annual_Report")
    return None

def get_existing_documents():
    """Retrieves all existing documents from the vector database"""
    try:
        response = requests.get(f"{API_BASE}/documents")
        response.raise_for_status()
        # Parse the JSON response properly
        documents = response.json()
        # Make sure we're working with the right data structure
        if isinstance(documents, str):
            # If the API returns a string instead of parsed JSON
            import json
            try:
                documents = json.loads(documents)
            except:
                print("Failed to parse API response as JSON")
                return []
        
        # Handle the case where the response might be nested
        if isinstance(documents, dict) and 'documents' in documents:
            documents = documents['documents']
            
        return documents
    except Exception as e:
        print(f"Error retrieving document list: {str(e)}")
        return []

def find_company_documents(company_name, existing_docs):
    """Find documents related to a specific company in the existing documents list"""
    normalized_name = normalize_company_name(company_name)
    company_docs = []
    
    print(f"Looking for documents matching company: {company_name}")
    print(f"Existing documents format: {type(existing_docs)}")
    
    # Add debug information
    if existing_docs and len(existing_docs) > 0:
        print(f"Sample document: {existing_docs[0]}")
    
    # Handle different potential formats
    for doc in existing_docs:
        # Handle case where doc might be a string or other type
        if not isinstance(doc, dict):
            print(f"Skipping non-dictionary document: {doc}")
            continue
            
        filename = doc.get("file_name", "")
        if filename:
            filename = filename.lower()
            if normalized_name in normalize_company_name(filename):
                company_docs.append(doc)
    
    return company_docs

def upload_and_get_doc_id(file_path: str) -> str:
    """Upload document and return doc_id"""
    try:
        with open(file_path, 'rb') as f:
            upload_response = requests.post(
                f"{API_BASE}/upload/",
                files={'file': f},
                headers={'Accept': 'application/json'}
            )
        upload_response.raise_for_status()
        data = upload_response.json()
        doc_id = data.get('doc_id')

        if doc_id:
            print(f"Document {file_path} uploaded and processed. doc_id: {doc_id}")
            return doc_id
        else:
            print(f"Upload response missing doc_id: {data}")
            return None

    except Exception as e:
        print(f"Failed to upload {file_path}: {str(e)}")
        return None

class HybridSearch:
    def __init__(self, api_base: str = API_BASE):
        self.api_base = api_base
        self.default_headers = {"Accept": "application/json"}
        
    def _query_source(self, params: Dict[str, Any]) -> str:
        try:
            # Properly handle list of doc_ids
            query_params = []
            for key, value in params.items():
                if isinstance(value, list):
                    for item in value:
                        query_params.append((key, item))
                else:
                    query_params.append((key, value))

            response = requests.get(
                f"{self.api_base}/query/",
                params=query_params,
                headers=self.default_headers
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            print(f"Error querying {params.get('search_type', 'unknown')}: {str(e)}")
            return ""
        except Exception as e:
            print(f"Unexpected error: {str(e)}")
            return ""

    def query_documents(self, query: str, doc_ids: List[str] = None) -> str:
        params = {
            "query": query,
            "search_type": "documents",
            "doc_ids": doc_ids or [],
            "top_k_docs": 7,
            "prompt_instructions": "Focus strictly on factual information from company documents."
        }
        return self._query_source(params)

    def query_web(self, query: str, domain: str = None) -> str:
        params = {
            "query": query,
            "search_type": "domain" if domain else "web",
            "target_domain": domain,
            "top_k_web": 5,
            "prompt_instructions": "Include latest market trends and competitive landscape."
        }
        return self._query_source(params)

    def hybrid_search(self, document_query: str, web_query: str, doc_ids: List[str] = None, domain: str = None) -> str:
        doc_results = self.query_documents(document_query, doc_ids)
        web_results = self.query_web(web_query, domain)

        return self._synthesize_results(doc_results, web_results)

    def _synthesize_results(self, doc_results, web_results):
        synthesis_prompt = f"""
        Combine insights from these two sources:
        
        Company Documents:
        {doc_results}
        
        Web Research:
        {web_results}
        
        Create a comprehensive answer that highlights:
        1. Key facts from official documents
        2. Market context from web sources
        3. Potential synergies between internal and external factors
        """
        
        return self._query_source({
            "query": synthesis_prompt,
            "search_type": "web",
            "top_k_web": 5,
            "prompt_instructions": "Synthesize key points without speculation"
        })

def retrieve_company_documents(company_name):
    """Retrieve documents for a company, checking existing ones first"""
    print(f"\n{'='*40}")
    print(f"Retrieving documents for {company_name}")
    print(f"{'='*40}\n")
    
    # Get existing documents
    print("Checking for existing company documents...")
    existing_docs = get_existing_documents()
    company_docs = find_company_documents(company_name, existing_docs)
    
    if company_docs:
        print(f"Found {len(company_docs)} existing documents for {company_name}:")
        for doc in company_docs:
            print(f"- {doc['file_name']} (ID: {doc['doc_id']})")
        
        # Return the doc_ids of existing documents
        return [doc["doc_id"] for doc in company_docs]
    
    print("No existing documents found. Retrieving new documents...")
    
    # Download new documents
    results = {
        'sec_10k': None,
        'web_report': None
    }
    
    # Download SEC 10-K filing
    print("\n=== 1. Checking SEC EDGAR database for 10-K ===\n")
    results['sec_10k'] = download_sec_10k(company_name)
    
    # Download annual report from company website
    print("\n=== 2. Searching web for annual report PDF ===\n")
    results['web_report'] = download_web_annual_report(company_name)
    
    # Upload documents and collect doc_ids
    doc_ids = []
    for report_type, report_path in results.items():
        if report_path:
            doc_id = upload_and_get_doc_id(report_path)
            if doc_id:
                doc_ids.append(doc_id)
    
    # Print summary
    print("\n=== Document Retrieval Results ===")
    print(f"SEC 10-K: {'Success: ' + results['sec_10k'] if results['sec_10k'] else 'Not found'}")
    print(f"Web Annual Report: {'Success: ' + results['web_report'] if results['web_report'] else 'Not found'}")
    
    return doc_ids

# Predefined questions for company analysis
ANALYSIS_QUESTIONS = [
    {
        "question": "What was the company's revenue and net income for the most recent fiscal year?",
        "web_domain": "bloomberg.com"
    },
    {
        "question": "What are the company's main products or services and their market segments?",
        "web_domain": "reuters.com"
    },
    {
        "question": "What are the key risks and challenges mentioned in the company's annual report?",
        "web_domain": None
    },
    {
        "question": "Who are the company's main competitors and what is their market share?",
        "web_domain": "marketwatch.com"
    }
]

def analyze_company_with_preset_questions(company_name: str):
    """Analyze a company using the preset questions"""
    # First, retrieve and manage company documents
    doc_ids = retrieve_company_documents(company_name)
    
    if not doc_ids:
        print("No documents available for analysis.")
        return None
    
    # Initialize search tool
    search_tool = HybridSearch()
    
    # Process each question
    results = {}
    for i, question_data in enumerate(ANALYSIS_QUESTIONS, 1):
        question = question_data["question"]
        web_domain = question_data["web_domain"]
        
        print(f"\n{'='*40}")
        print(f"Question {i}: {question}")
        if web_domain:
            print(f"Using domain: {web_domain}")
        print(f"{'='*40}\n")
        
        # Run hybrid search for this question
        result = search_tool.hybrid_search(
            document_query=question,
            web_query=f"{company_name} {question}",
            doc_ids=doc_ids,
            domain=web_domain
        )
        
        results[question] = result
        print(f"\nAnalysis for Question {i}:")
        print(result)
    
    return results

def interactive_company_analysis():
    """Interactive function to analyze companies with preset questions"""
    print("\n==== Company Financial Analysis Tool ====\n")
    print("Available questions for analysis:")
    
    for i, question_data in enumerate(ANALYSIS_QUESTIONS, 1):
        print(f"{i}. {question_data['question']}")
        if question_data['web_domain']:
            print(f"   Domain: {question_data['web_domain']}")
    
    while True:
        company_name = input("\nEnter company name (or 'quit' to exit): ")
        if company_name.lower() == 'quit':
            break
        
        print("\nRunning analysis with preset questions...")
        results = analyze_company_with_preset_questions(company_name)
        
        print("\n==== Analysis Complete ====\n")

# Example Usage
if __name__ == "__main__":
    interactive_company_analysis()