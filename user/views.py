import json
from django.shortcuts import render
from django.http import JsonResponse
from rest_framework_simplejwt.tokens import RefreshToken
from .models import User
# Create your views here.

#회원가입
def SignUp(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        name = data.get('name','')
        employee_number = data.get('employee_number','')
        phone_number = data.get("phone_number",'')

        user = User.objects.get(name=name, employee_number=employee_number)

        if user is not None: #이미 있다면 가입된유저이다
            return JsonResponse({'message': '이미 가입된 상태입니다.'})

        #user가 None이면 미가입유저이기에 user를 생성해서 가입시킨다.
        User.objects.create(
            name = name,
            employee_number = employee_number,
            phone_number = phone_number
        )

        return JsonResponse({'success': True, 'message': '가입에 성공하였습니다.'})
    else:
        return JsonResponse({'success': False, 'message': '잘못된 요청입니다.'})

#로그인
def Login(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        name = data.get('name','')
        employee_number = data.get('employee_number')

        #UserDB에서 사용자 확인
        user = User.objects.get(name=name, employee_number=employee_number)
        if user is not None:
            #사용자 있음
            refresh = RefreshToken.for_user(user)
            return JsonResponse({
                'success': True,
                'access': str(refresh.access_token),
                'refresh': str(refresh),
                'name': user.name,
                'employee_number': user.employee_number,
                'department_code': user.department_code
            })
        else:
            #사용자 없음
            return JsonResponse({'success': False, 'message': "로그인 실패\n이름이나 사원번호를 확인해주세요."})
    else:
        return JsonResponse({'success': False, 'message': '잘못된 요청 방식입니다.'})