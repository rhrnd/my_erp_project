from django import template

register = template.Library()


@register.filter
def get_item(dictionary, key):
    """딕셔너리에서 변수 키로 값을 가져오는 필터"""
    if isinstance(dictionary, dict):
        # 키가 숫자(int)로 들어올 수도 있으므로 체크
        return dictionary.get(key) or dictionary.get(str(key))
    return ""


@register.filter
def blank(value):
    """None, 'None' 문자열, 빈 값을 모두 빈 문자열로 변환"""
    if value is None or str(value).strip() in ('None', ''):
        return ''
    return value
