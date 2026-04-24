import os
import re

def split_manual(input_file, output_dir, source_url, manual_type="GL"):
    """
    Splits a monolithic markdown manual into granular sections based on headers.
    Injects metadata for Bedrock RAG attribution.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    with open(input_file, 'r', encoding='utf-8') as f:
        content = f.read()

    # Split by major headers (e.g., # _Header_ or ### Header)
    # This pattern looks for lines starting with one or more # followed by a heading
    sections = re.split(r'\n(?=#+\s*|_)', content)

    print(f"Detected {len(sections)} potential sections in {input_file}.")

    for i, section in enumerate(sections):
        section = section.strip()
        if not section:
            continue

        # Extract a clean filename from the first line (the header)
        first_line = section.split('\n')[0]
        # Clean special chars and spaces
        filename_base = re.sub(r'[^\w\s-]', '', first_line).strip().lower().replace(' ', '_')
        
        # TRUNCATE filename to 50 chars to avoid Windows path limit errors
        filename_base = filename_base[:50].strip('_')

        # If the header is too short/empty, use a number
        if not filename_base or len(filename_base) < 3:
            filename_base = f"section_{i+1}"
        
        filename = f"{filename_base}.md"
        filepath = os.path.join(output_dir, filename)

        # Build the metadata-injected content
        injected_content = [
            f"SOURCE_URL: {source_url}",
            f"MANUAL_TYPE: {manual_type}",
            f"SECTION: {first_line.strip('# _').strip()}",
            "---",
            section
        ]

        with open(filepath, 'w', encoding='utf-8') as f:
            f.write('\n'.join(injected_content))

    print(f"Done! Split into {len(os.listdir(output_dir))} files in {output_dir}")

if __name__ == "__main__":
    # EXAMPLE USAGE for your Property Manual:
    # 1. Save your property manual as 'data/property_manual.md'
    # 2. Run this script:
    
    split_manual(
        input_file='data/property.md', 
        output_dir='data/bedrock_ingest/property_sections',
        source_url='https://bindingauthority.coactionspecialty.com/manuals/property.html',
        manual_type="Property"
    )
    
    # For now, I'll keep it as a template. You can edit the paths below:
    print("Script loaded. Edit the __main__ block to point to your manual file.")
