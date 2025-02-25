# idea: have linkchecker perform automatic validations:
# https://github.com/validator/validator/wiki/Service-%C2%BB-Input-%C2%BB-POST-body

import requests
from pprint import pprint

validator_url = "https://validator.w3.org/nu/?out=json"
page_content = """
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>Test document</title>
  </head>
  <body>
    <img id="background image" src="background.png">
  </body>
</html>
"""

response = requests.post(
    validator_url,
    data=page_content,
    headers={'Content-Type': 'text/html; charset=utf-8'},
    timeout=60,
)
pprint(response.json())

result = """
{'messages': [{'extract': '>\n'
                          '        <img id="background image" '
                          'src="background.png">\n'
                          '     ',
               'firstColumn': 9,
               'hiliteLength': 48,
               'hiliteStart': 10,
               'lastColumn': 56,
               'lastLine': 9,
               'message': 'Bad value “background image” for attribute “id” on '
                          'element “img”: An ID must not contain whitespace.',
               'type': 'error'},
              {'extract': '>\n'
                          '        <img id="background image" '
                          'src="background.png">\n'
                          '     ',
               'firstColumn': 9,
               'hiliteLength': 48,
               'hiliteStart': 10,
               'lastColumn': 56,
               'lastLine': 9,
               'message': 'An “img” element must have an “alt” attribute, '
                          'except under certain conditions. For details, '
                          'consult guidance on providing text alternatives for '
                          'images.',
               'type': 'error'}]}
"""
