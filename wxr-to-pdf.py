# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# Copyright (C) 2024 Fergcorp, LLC
#
# For more information, please contact:
# Andrew Ferguson
# andrew@fergcorp.com

"""
Description:
This program converts a WordPress WXR (WordPress eXtended RSS) file to a PDF document.
It parses the WXR file to extract blog posts and pages, including their content,
authors, publication dates, and comments. The extracted data is then formatted and
written to a PDF file, which includes a title page, a table of contents, and the content
of each post and page. The program can be run from the command line with the WXR file
and output PDF file specified as arguments.

Getting started:

Contents of the wp-content/uploads folder needs to be in ./content
You will need to download DejaVu font and put it in ./fonts: https://dejavu-fonts.github.io/


# Create a virtual environment
python -m venv env

# Activate the virtual environment
# On Windows
.\env\Scripts\activate
# On macOS and Linux
source env/bin/activate

# Install required packages
pip install -r requirements.txt

# Run the script
python wxr-to-pdf.py -i path_to_wxr_file -o output_pdf_file

# Deactivate the virtual environment when done
deactivate
"""

import argparse
import re
import xml.etree.ElementTree as ET
from fpdf import FPDF
from fpdf.enums import XPos, YPos
from datetime import datetime
import pytz


class PDF(FPDF):

    def __init__(self, title, description, date_range, url):
        super().__init__()
        self.title = title
        self.description = description
        self.date_range = date_range
        self.url = url
        self.toc = []  # Initialize the Table of Contents list

    def header(self):
        if self.page_no() < 5:
            return  # No header on the first page (title page)
        self.set_font('DejaVu', 'I', 8)
        self.cell(0, 10, f"{self.title} - {self.description}", 0, align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def footer(self):
        if self.page_no() == 1:
            return  # No footer on the first page (title page)
        self.set_y(-15)
        self.set_font('DejaVu', 'I', 8)
        self.cell(0, 10, f'Page {self.page_no()}', 0, align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)

    def chapter_body(self, body):
        self.set_font('DejaVu', '', 12)
        self.multi_cell(0, 10, body)
        self.ln(10)

    def add_title_page(self):
        self.add_page()
        self.set_font('DejaVu', 'B', 36)
        self.ln(100)
        self.cell(0, 10, self.title, 0, align='C')
        self.ln(20)
        self.set_font('DejaVu', '', 24)
        self.cell(0, 10, self.description, 0, align='C')
        self.ln(20)
        self.set_font('DejaVu', 'I', 14)
        self.cell(0, 10, self.date_range, 0, align='C')
        self.ln(20)
        self.set_font('DejaVu', '', 10)
        self.cell(0, 10, f"An archive of {self.url}", 0, align='C')
        self.ln(20)

    def add_toc_entry(self, title, page_number, link):
        self.toc.append((title, page_number, link))

    def generate_toc(self, pdf, outline):
        self.add_font('DejaVuSansMono', '', 'fonts/DejaVuSansMono.ttf')
        self.set_font('DejaVuSansMono', '', 12)
        for title, page_number, link in self.toc:
            toc_text = f'{title[:60]}'
            self.cell(0, 10, f"{toc_text}{'.' * ((70 - len(toc_text)))}{page_number}", 0, new_x=XPos.LMARGIN,
                      new_y=YPos.NEXT, link=link)


def parse_wxr(file_path, tz):
    tree = ET.parse(file_path)
    root = tree.getroot()

    # Extract the blog title and description
    channel = root.find('channel')
    blog_title = channel.find('title').text if channel.find('title') is not None else 'No Title'
    blog_description = channel.find('description').text if channel.find('description') is not None else ''
    url = channel.find('.//{http://wordpress.org/export/1.2/}base_blog_url').text

    # Extract author information
    author_map = {}
    for author in root.findall('.//{http://wordpress.org/export/1.2/}author'):
        author_login = author.find('{http://wordpress.org/export/1.2/}author_login').text
        author_display_name = author.find('{http://wordpress.org/export/1.2/}author_display_name').text
        author_map[author_login] = author_display_name

    posts = []
    pages = []
    dates = []

    for item in root.findall('.//item'):

        post_type = item.find('.//{http://wordpress.org/export/1.2/}post_type')
        status = item.find('.//{http://wordpress.org/export/1.2/}status')
        if post_type is None or status is None:
            continue

        post_type_text = post_type.text
        status_text = status.text

        if post_type_text not in ['post', 'page']:
            continue

        if status_text != 'publish':
            print(
                f"Unpublished item skipped: Title = {item.find('title').text if item.find('title') is not None else 'No Title'}, Status = {status_text}")
            continue

        title = item.find('title')
        title_text = title.text if title is not None else 'No Title'

        author_login = item.find('.//{http://purl.org/dc/elements/1.1/}creator')
        author_text = author_map.get(author_login.text,
                                     'Unknown Author') if author_login is not None else 'Unknown Author'

        pub_date = item.find('pubDate')
        pub_date_text = pub_date.text if pub_date is not None else 'Unknown Date'

        # Convert publication date to Pacific Time Zone
        if pub_date_text != 'Unknown Date':
            pub_date = datetime.strptime(pub_date_text, '%a, %d %b %Y %H:%M:%S %z')
            pub_date = pub_date.astimezone(pytz.timezone(tz))
            dates.append(pub_date)

        content = item.find('.//{http://purl.org/rss/1.0/modules/content/}encoded')
        content_text = content.text if content is not None else ''

        post_data = {
            'title': title_text,
            'author': author_text,
            'pub_date': pub_date,
            'content': content_text,
            'type': post_type_text,
            'comments': []
        }

        for comment in item.findall('.//{http://wordpress.org/export/1.2/}comment'):
            comment_author = comment.find('.//{http://wordpress.org/export/1.2/}comment_author').text
            comment_content = comment.find('.//{http://wordpress.org/export/1.2/}comment_content').text
            comment_date = comment.find('.//{http://wordpress.org/export/1.2/}comment_date').text
            comment_approved = comment.find('.//{http://wordpress.org/export/1.2/}comment_approved').text

            comment_date = datetime.strptime(comment_date, '%Y-%m-%d %H:%M:%S')
            comment_date = comment_date.astimezone(pytz.timezone('America/Los_Angeles'))
            comment_date = comment_date.strftime("%A, %B %-d, %Y @ %-I:%M %p")

            # Only add approved comments
            if comment_approved == '1':
                comment_data = {
                    'author': comment_author,
                    'content': comment_content,
                    'date': comment_date
                }
                post_data['comments'].append(comment_data)

        if post_type_text == 'post':
            posts.append(post_data)
        elif post_type_text == 'page':
            pages.append(post_data)

    date_range = f"{min(dates).strftime('%B %-d, %Y')} - {max(dates).strftime('%B %-d, %Y')}" if dates else 'N/A'
    return blog_title, blog_description, date_range, posts, pages, url


def replace_urls(content, url):
    # TODO: Figure out how to detect and replace links to posts with PDF link to page

    escaped_url = re.escape(url)
    modified_content = re.sub(
        fr'{escaped_url}/?wp-content/uploads/',
        './content/',
        content
    )
    # Used to see what URL for the site exist, might require manual editing
    match = re.search(fr'{escaped_url}/?[A-Za-z0-9/-]*', modified_content)
    if match:
        print(f"Found URL: {match.group()}")
    return modified_content


def replace_shortcode_captions(content):
    # Regular expression to match WordPress caption shortcodes
    pattern = re.compile(r'\[caption id="(.*?)" align="(.*?)" width="(.*?)"\](.*?)\[\/caption\]', re.DOTALL)

    # Function to convert the shortcode to HTML
    def replace_caption(match):
        id_attr = match.group(1)
        align = match.group(2)
        width = match.group(3)
        inner_content = match.group(4)

        # Extract the image and caption text
        inner_pattern = re.compile(r'(<img.*?\/>)(.*?)$', re.DOTALL)
        inner_match = inner_pattern.match(inner_content.strip())

        if inner_match:
            img_tag = inner_match.group(1).strip()
            caption_text = inner_match.group(2).strip()

            # Build the HTML
            html = f'<figure id="{id_attr}" class="{align}" style="width:{width}px">\n'
            html += f'  {img_tag}\n'
            html += f'  <figcaption>{caption_text}</figcaption>\n'
            html += '</figure>\n'

            return html
        else:
            return match.group(0)  # Return the original shortcode if no match

    # Replace all caption shortcodes in the content
    content = pattern.sub(replace_caption, content)

    return content


def convert_to_paragraphs(text):
    # Split the text by double line breaks
    paragraphs = text.split('\n\n')
    # Wrap each paragraph with <p> tags
    paragraphs = [f'<p>{paragraph.strip()}</p>' for paragraph in paragraphs]
    # Join the paragraphs back together with a newline in between
    return '\n'.join(paragraphs)


def preprocess_content(content, url):
    # Replace WordPress caption shortcodes with HTML
    content = replace_shortcode_captions(content)

    content = replace_urls(content, url)

    # Convert paragraphs
    content = convert_to_paragraphs(content)

    return content


def preprocess_comments(comments):
    html_comments = f'<h3>Comments ({str(len(comments))})</h3>'
    if len(comments):
        for comment in comments:
            # This is specific to a plugin I had that would cross post to Facebook and slurp in comments/likes
            if re.search(r'liked this on Facebook\.', str(comment["content"])):
                html_comments += f'<div class="comment"><p><strong>{comment["author"]}</strong> give this a <strong>LIKE</strong> on Facebook!</p></div>'
            else:
                html_comments += f'<div class="comment"><p><strong>{comment["author"]}</strong> on {comment["date"]}:</p>'
                html_comments += f'<p>{re.sub("<[^<]+?>", "", str(comment["content"]))}</p></div>'
        return html_comments
    else:
        return ""


def create_pdf(blog_title, blog_description, date_range, posts, pages, url, output_path):
    pdf = PDF(blog_title, blog_description, date_range, url)
    pdf.set_auto_page_break(auto=True, margin=15)

    # Add the DejaVu font
    pdf.add_font('DejaVu', '', 'fonts/DejaVuSans.ttf')
    pdf.add_font('DejaVu', 'B', 'fonts/DejaVuSans-Bold.ttf')
    pdf.add_font('DejaVu', 'I', 'fonts/DejaVuSans-Oblique.ttf')
    pdf.add_font('DejaVu', 'BI', 'fonts/DejaVuSans-BoldOblique.ttf')

    # Add title page
    pdf.add_title_page()

    # Insert ToC placeholder
    pdf.add_page()
    pdf.insert_toc_placeholder(render_toc_function=pdf.generate_toc, pages=3)

    # Uncomment if you want to include a page saying these are posts, not pages
    # pdf.add_page()
    # # Uncomment the following if the "Posts" page should be included in the TOC
    # # page_number = pdf.page_no()
    # # link = pdf.add_link()
    # # pdf.add_toc_entry("Posts", page_number, link)
    # pdf.set_font('DejaVu', 'B', 36)
    # pdf.ln(100)
    # pdf.cell(0, 10, "Posts", 0, align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    # pdf.set_font('DejaVu', '', 12)
    # pdf.cell(0, 10, "These are posts (separate from blog pages) on the site.", 0, align='C')

    def add_content(items, item_type="post"):
        for item in items:
            title = item['title']
            author = item['author']
            pub_date = item['pub_date']
            content = preprocess_content(item['content'], url)
            comments_html = preprocess_comments(item['comments'])
            full_content = content + comments_html

            pdf.add_page()
            page_number = pdf.page_no()
            link = pdf.add_link()
            if item_type == "page":
                pdf.add_toc_entry(f"Page: {title}", page_number, link)
            else:
                pdf.add_toc_entry(title, page_number, link)

            pdf.set_font('DejaVu', 'B', 20)
            pdf.cell(0, 10, title, 0, new_x=XPos.LMARGIN, new_y=YPos.NEXT, link=link)

            pdf.set_font('DejaVu', 'I', 12)
            pdf.cell(0, 10, f'By {author} on {pub_date.strftime("%A, %B %-d, %Y @ %-I:%M %p")}', 0, new_x=XPos.LMARGIN,
                     new_y=YPos.NEXT)
            pdf.ln(5)

            pdf.set_font('DejaVu', '', 12)
            pdf.write_html(full_content,
                           ul_bullet_char="•",
                           li_prefix_color="#000000",
                           tag_indents={"blockquote": 20},
                           )
            pdf.ln(10)

    # Add posts first
    add_content(posts)

    pdf.add_page()
    # Uncomment the following if the "Pages" page should be included in the TOC
    # page_number = pdf.page_no()
    # link = pdf.add_link()
    # pdf.add_toc_entry("Pages", page_number, link)
    pdf.set_font('DejaVu', 'B', 36)
    pdf.ln(100)
    pdf.cell(0, 10, "Pages", 0, align='C', new_x=XPos.LMARGIN, new_y=YPos.NEXT)
    pdf.set_font('DejaVu', '', 12)
    pdf.cell(0, 10, "These are pages (separate from blog posts) on the site.", 0, align='C')

    # Add pages at the end
    add_content(pages, item_type="page")

    pdf.output(output_path)


if __name__ == '__main__':
    # Setup argument parser
    parser = argparse.ArgumentParser(description="Convert a WordPress WXR file to a PDF document.")
    parser.add_argument('-i', '--wxr_file', type=str, help='Path to the WordPress WXR file')
    parser.add_argument('-o', '--output_pdf', type=str, help='Path to the output PDF file')
    parser.add_argument('-tz', '--timezone', type=str, help='Timezone of blog, e.g. "America/Los_Angeles"',
                        default="America/Los_Angeles", required=False)

    # Parse arguments
    args = parser.parse_args()
    wxr_file = args.wxr_file
    output_pdf = args.output_pdf
    tz = args.timezone

    # Process WXR file and create PDF
    blog_title, blog_description, date_range, posts, pages, url = parse_wxr(wxr_file, tz)

    create_pdf(blog_title, blog_description, date_range, posts, pages, url, output_pdf)
    print(f'PDF created: {output_pdf}')
