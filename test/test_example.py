from bing_api.parsers.html_parsers import extract_job_id_from_html, extract_video_cards_from_html
from bing_api.parsers.json_parsers import parse_video_detail_payload


def test_extract_video_card_from_html():
    html = (
        '<div id="gir_async">'
        '<a aria-label="demo" '
        'href="/images/create/foo/4-69ac31fe01a74943955627343a0ba067?id=31ad396e7705b83417cf&view=detailv2&idpp=genimg&datatype=video&thId=OIG4.demo&FORM=GCRIDP">'
        '<img src="https://th.bing.com/th/id/OIG4.thumb?pid=videocreator" />'
        '</a>'
        '</div>'
    )
    cards = extract_video_cards_from_html(html)
    assert len(cards) == 1
    assert cards[0].image_id == "31ad396e7705b83417cf"
    assert cards[0].th_id == "OIG4.demo"
    assert cards[0].thumbnail_url == "https://th.bing.com/th/id/OIG4.thumb?pid=videocreator"
    assert extract_job_id_from_html(html) == "4-69ac31fe01a74943955627343a0ba067"


def test_parse_video_detail_payload():
    payload = {
        "value": [
            {
                "contentUrl": "https://th.bing.com/th/id/OIG4.demo?pid=videocreator",
                "thumbnailUrl": "https://th.bing.com/th/id/OIG4.thumb?pid=ImgGn",
                "imageId": "31ad396e7705b83417cf",
                "name": "demo",
                "encodingFormat": "mp4",
                "width": 854,
                "height": 480,
                "hostPageUrl": "https://www.bing.com/images/create/demo",
                "generationMetadata": {
                    "modelName": "SoraV2",
                    "copyrightAttr": "Powered by Sora 2",
                },
            }
        ]
    }
    details = parse_video_detail_payload(payload)
    assert len(details) == 1
    assert details[0].image_id == "31ad396e7705b83417cf"
    assert details[0].content_url.endswith("pid=videocreator")
    assert details[0].model_name == "SoraV2"
