# 파일명 변경: 이 파일을 '보고서' 폴더에 넣고 우클릭 > PowerShell로 실행
$dir = $PSScriptRoot
$old = Join-Path $dir '업무체크_케이터링팀_2026-10-02.xlsx'; $new = '261002_업무체크_케이터링팀.xlsx'
if (Test-Path -LiteralPath $old) { Rename-Item -LiteralPath $old -NewName $new; Write-Host "변경: $new" } else { Write-Host "없음(건너뜀): 업무체크_케이터링팀_2026-10-02.xlsx" }
$old = Join-Path $dir '영업당직_근무매뉴얼.xlsx'; $new = '261012_영업당직_근무매뉴얼.xlsx'
if (Test-Path -LiteralPath $old) { Rename-Item -LiteralPath $old -NewName $new; Write-Host "변경: $new" } else { Write-Host "없음(건너뜀): 영업당직_근무매뉴얼.xlsx" }
$old = Join-Path $dir '웰스토리_미팅자료_2026-10-07_v2.xlsx'; $new = '261007_웰스토리_미팅자료_v2.xlsx'
if (Test-Path -LiteralPath $old) { Rename-Item -LiteralPath $old -NewName $new; Write-Host "변경: $new" } else { Write-Host "없음(건너뜀): 웰스토리_미팅자료_2026-10-07_v2.xlsx" }
$old = Join-Path $dir '전략상품_10월보고.xlsx'; $new = '261002_전략상품_10월보고.xlsx'
if (Test-Path -LiteralPath $old) { Rename-Item -LiteralPath $old -NewName $new; Write-Host "변경: $new" } else { Write-Host "없음(건너뜀): 전략상품_10월보고.xlsx" }
$old = Join-Path $dir '케이터링팀_미팅자료_2026-10-06.xlsx'; $new = '261006_케이터링팀_미팅자료.xlsx'
if (Test-Path -LiteralPath $old) { Rename-Item -LiteralPath $old -NewName $new; Write-Host "변경: $new" } else { Write-Host "없음(건너뜀): 케이터링팀_미팅자료_2026-10-06.xlsx" }
$old = Join-Path $dir '케이터링팀_업무체크_발표자료.xlsx'; $new = '261002_케이터링팀_업무체크_발표자료.xlsx'
if (Test-Path -LiteralPath $old) { Rename-Item -LiteralPath $old -NewName $new; Write-Host "변경: $new" } else { Write-Host "없음(건너뜀): 케이터링팀_업무체크_발표자료.xlsx" }
Read-Host '완료. Enter를 누르면 닫힙니다'
