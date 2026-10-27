# 회의록 폴더 정리: 이 파일을 '클로드 코워크\회의록' 폴더에 넣고 우클릭 > PowerShell로 실행
# 날짜(YYMMDD)가 붙은 파일을 'YYMMDD_주제 회의' 폴더로 옮긴다. 목록에 없는 파일은 건드리지 않는다.
$dir = $PSScriptRoot
$map = [ordered]@{
  '261012_상황근무개선_회의록.xlsx'        = '261012_상황근무개선 회의'
  '261016_회의록_수입참치캔검토.xlsx'      = '261016_수입참치캔 회의'
  '261016_회의록_수입파스타검토.xlsx'      = '261016_수입파스타 회의'
  '261022_회의록_소울푸드베트남전류검토.xlsx' = '261022_소울푸드 회의'
  '261023_소울푸드미팅보고서.xlsx'          = '261022_소울푸드 회의'
}
foreach ($name in $map.Keys) {
  $src = Join-Path $dir $name
  $dstDir = Join-Path $dir $map[$name]
  if (Test-Path -LiteralPath $src) {
    New-Item -ItemType Directory -Force -Path $dstDir | Out-Null
    $dst = Join-Path $dstDir $name
    if (Test-Path -LiteralPath $dst) { Write-Host "이미 있음(건너뜀): $name" }
    else { Move-Item -LiteralPath $src -Destination $dst; Write-Host "이동: $name -> $($map[$name])" }
  } else { Write-Host "없음(건너뜀): $name" }
}
Read-Host '완료. Enter를 누르면 닫힙니다'
