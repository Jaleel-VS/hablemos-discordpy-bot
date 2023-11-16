from os import path
# import imgkit
from html2image import Html2Image

dir_path = path.dirname(path.dirname(path.realpath(__file__))).replace('\\', '/')


def create_image(user_name, user_avatar, message_content):
    # options formerly for imgkit package

    # options = {
    #     'format': 'png',
    #     'crop-w': '644',
    #     'encoding': "UTF-8",
    #     'enable-local-file-access': None,
    #     'transparent': None,
    # }

    font_size = ""

    font_sizes = {
        75: 'x-large',
        110: 'large',
        150: 'medium',
    }

    for fs in font_sizes:
        if len(message_content) <= fs:
            font_size = font_sizes[fs]
            break

    html = f'''
            <html>
            <head>
            <style>   
        @font-face {{
        font-family: 'Satisfy Pro';
        src: url('file:///{dir_path}/quote_generator_helper/fonts/SatisfyPro.eot');
        src: url('file:///{dir_path}/quote_generator_helper/fonts/SatisfyPro.eot?#iefix') format('embedded-opentype'),
             url('file:///{dir_path}/quote_generator_helper/fonts/SatisfyPro.woff') format('woff'),
             url('file:///{dir_path}/quote_generator_helper/fonts/SatisfyPro.ttf') format('truetype'),
             url('file:///{dir_path}/quote_generator_helper/fonts/SatisfyPro.svg#SatisfyPro') format('svg');
        font-weight: normal;
        font-style: normal;
        font-display: swap;
        }}
        
        @font-face {{
        font-family: 'Helvetica Neue';
        src: url('file:///{dir_path}/quote_generator_helper/fonts/HelveticaNeue-Roman.eot');
        src: url('file:///{dir_path}/quote_generator_helper/fonts/HelveticaNeue-Roman.eot?#iefix') format('embedded-opentype'),
             url('file:///{dir_path}/quote_generator_helper/fonts/HelveticaNeue-Roman.woff') format('woff'),
             url('file:///{dir_path}/quote_generator_helper/fonts/HelveticaNeue-Roman.ttf') format('truetype'),
             url('file:///{dir_path}/quote_generator_helper/fonts/HelveticaNeue-Roman.svg#HelveticaNeue-Roman') format('svg');
        font-weight: normal;
        font-style: normal;
        font-display: swap;
        }}
        
        .fullquote {{
        border: 4px solid #fff;
        border-radius: 10px;
        width: 634px;
        height: 256px;
        
        -webkit-filter: grayscale(100%);
        filter: grayscale(100%);
        }}
        
        .myImage {{
            float: left;
            
            border-right: 0;
            border-top-left-radius: 8px;
            border-bottom-left-radius: 8px;
            width: 258px;
            height: 256px;
            
            -webkit-filter: grayscale(100%);
            filter: grayscale(100%);
            }}
        
        
            .quote {{
                float: left;
                width: 376px;
                height: 256px;
                margin-top: 0;
                margin-bottom: 0;
                background-color: #0c0c0c;
                border-left: 0;
                border-top-right-radius: 8px;
                border-bottom-right-radius: 8px;
        
                text-align: center;
                }}
        
            .main-quote {{
            color: white;
            font-family: Helvetica Neue;
            font-size: {font_size};
            padding: 10% 5% 5%;
            }}
        
            
        
            .author {{
                color: white;
                font-size: 135%;
                font-family: Satisfy Pro;
            }}
        
            span:after,
        span:before{{
            content:"\\00a0\\00a0\\00a0\\00a0\\00a0";
            text-decoration:line-through;
        }}
        
        body {{
            padding: 0;
            margin: 0;
            background-color: transparent;
        }}
            </style>
            </head>
            <body>
            <div class="fullquote">
                <img src="{user_avatar}" class="myImage"/>
                <div class="quote">
                    <p class="main-quote">{message_content}</p>
                    <p class="author"><span> {user_name} </span></p>
                </div>
            </div>
            </body>
            </html>
        '''

    img_dir = f"{dir_path}/quote_generator_helper"
    img_path = f"{img_dir}/picture.png"
    hti = Html2Image(size=(644, 264), output_path=img_dir)
    try:
        hti.screenshot(html_str=html, save_as="picture.png")
        # imgkit.from_string(html, img_path, options=options)  # , config=config)
    except OSError:
        raise OSError("\n\nYou need to install wkhtmltoimage. Go to https://wkhtmltopdf.org/downloads.html and place \n"
                      "the binary somewhere that `which wkhtmltoimage` (Linux) or `where wkhtmltoimage` (Windows) \n"
                      "can find it (you may need to add it to your system path).")
    return img_path


# for testing
create_image('Priúñaku',
             'https://cdn.discordapp.com/avatars/166580565548466176/a106c3ab56c9c99d48b437b05a5552e4.png?size=256',
             'Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed euismod, nunc vel ultricies ultricies')
