import subprocess

def create_image(user_name, user_avatar_url, message_content):
    # Your HTML template with placeholders for user_name, user_avatar_url, and message_content
    html_template = f'''
        <html>
        <head>
            <style>
                .grayscale-image {{
                     -webkit-filter: grayscale(1); /* Webkit */
                    filter: gray; /* IE6-9 */
                    filter: grayscale(1); /* W3C */
                }}
            </style>
        </head>
        <body>
            <img src="{user_avatar_url}" alt="{user_name}" class="grayscale-image"/>
            <p>{message_content}</p>
        </body>
        </html>
    '''

    # Write the HTML content to a file
    with open('input.html', 'w') as html_file:
        html_file.write(html_template)

    # Use subprocess to call the wkhtmltoimage command.
    subprocess.run(['wkhtmltoimage', 'input.html', 'output.png'])

    # Optional: Clean up the input HTML file after generating the image
    subprocess.run(['rm', 'input.html'])

    return 'output.png'

# Test the function
user_name = 'Priúñaku'
user_avatar_url = 'https://www.citizen.co.za/rekord/wp-content/uploads/sites/85/2022/08/Rekord-LL-image-780x470.jpg'
message_content = 'Hello from the other side'

image_path = create_image(user_name, user_avatar_url, message_content)
print(f'Image generated: {image_path}')
