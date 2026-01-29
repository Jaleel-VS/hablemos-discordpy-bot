from os import path
import imgkit
import logging

logger = logging.getLogger(__name__)

dir_path = path.dirname(path.realpath(__file__))


def create_image(user_name, user_avatar, message_content):
    logger.info(f"create_image called: user_name={user_name!r}, message_content={message_content!r}")
    options = {
        'format': 'png',
        'crop-w': '644',
        'encoding': "UTF-8",
        'enable-local-file-access': None,
    }

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
        src: url('{dir_path}/fonts/SatisfyPro.eot');
        src: url('{dir_path}/fonts/SatisfyPro.eot?#iefix') format('embedded-opentype'),
             url('{dir_path}/fonts/SatisfyPro.woff') format('woff'),
             url('{dir_path}/fonts/SatisfyPro.ttf') format('truetype'),
             url('{dir_path}/fonts/SatisfyPro.svg#SatisfyPro') format('svg');
        font-weight: normal;
        font-style: normal;
        font-display: swap;
    }}
    
    @font-face {{
        font-family: 'Helvetica Neue';
        src: url('{dir_path}/fonts/HelveticaNeue-Roman.eot');
        src: url('{dir_path}/fonts/HelveticaNeue-Roman.eot?#iefix') format('embedded-opentype'),
             url('{dir_path}/fonts/HelveticaNeue-Roman.woff') format('woff'),
             url('{dir_path}/fonts/HelveticaNeue-Roman.ttf') format('truetype'),
             url('{dir_path}/fonts/HelveticaNeue-Roman.svg#HelveticaNeue-Roman') format('svg');
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

    img_path = f"{dir_path}/picture.png"
    imgkit.from_string(html, img_path, options=options)
    return img_path

# for testing
if __name__ == "__main__":  
    create_image('Priúñaku',
                'https://cdn.discordapp.com/avatars/166580565548466176/a106c3ab56c9c99d48b437b05a5552e4.png?size=256',
                'Lorem ipsum dolor sit amet, consectetur adipiscing elit. Sed euismod, nunc vel ultricies ultricies')




