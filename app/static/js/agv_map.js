const canvas = document.getElementById('mapCanvas');
const ctx = canvas.getContext('2d');

// AGV 아이콘 그리는 함수
function drawAGV(x, y) {
    ctx.clearRect(0, 0, canvas.width, canvas.height);  // 캔버스 초기화
    const agvSize = 15;

    // 맵 이미지 다시 그릴 필요 없이 배경 유지됨
    ctx.beginPath();
    ctx.arc(x, y, agvSize, 0, 2 * Math.PI);
    ctx.fillStyle = 'red';
    ctx.fill();
}

// AGV 좌표를 주기적으로 서버에서 받아오기
function updateAGV() {
    fetch('/api/agv_position')
        .then(res => res.json())
        .then(data => {
            drawAGV(data.x, data.y);
        });
}

setInterval(updateAGV, 1000);  // 1초마다 갱신