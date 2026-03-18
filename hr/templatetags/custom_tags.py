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


@register.filter
def is_dict(value):
    """값이 딕셔너리인지 확인"""
    return isinstance(value, dict)


@register.filter
def split(value, arg):
    """문자열을 구분자로 분리해 리스트 반환"""
    return str(value).split(arg)


_FIELD_LABEL_MAP = {
    'name': '이름',
    'phone': '연락처',
    'address': '주소',
    'position': '직급',
    'join_date': '입사일',
    'retire_date': '퇴사일',
    'dept': '부서',
    'emp_id': '사원번호',
    'status': '재직상태',
    'change_reason': '변경사유',
    'in_use': '사용여부',
    'comp': '소속회사명',
    'id': '부서코드',
    'resident_number': '주민등록번호',
}


@register.filter
def field_label(value):
    """영문 필드명을 한글 레이블로 변환"""
    return _FIELD_LABEL_MAP.get(str(value), value)
