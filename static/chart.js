const ctx = document.getElementById('sensorChart').getContext('2d');
const chartData = {
  labels: [],
  datasets: [
    {
      label: 'Suhu (°C)',
      data: [],
      borderColor: '#0f9d58',
      backgroundColor: 'rgba(15,157,88,0.12)',
      tension: 0.4,
      fill: false,
    },
    {
      label: 'Kelembapan (%)',
      data: [],
      borderColor: '#34c759',
      backgroundColor: 'rgba(52,199,89,0.12)',
      tension: 0.4,
      fill: false,
    }
    ,
    {
      label: 'Water Level (cm)',
      data: [],
      borderColor: '#1779ba',
      backgroundColor: 'rgba(23,121,186,0.12)',
      tension: 0.4,
      fill: false,
    }
    ,
    {
      label: 'pH',
      data: [],
      borderColor: '#ff9800',
      backgroundColor: 'rgba(255,152,0,0.12)',
      tension: 0.4,
      fill: false,
    }
  ]
};
const sensorChart = new Chart(ctx, {
  type: 'line',
  data: chartData,
  options: {
    responsive: true,
    plugins: {
      legend: { display: true }
    },
    scales: {
      x: { display: true, title: { display: true, text: 'Waktu' } },
      y: { display: true, title: { display: true, text: 'Nilai' } }
    }
  }
});

function formatToWIB(ts, short=false) {
  if (!ts) return null;
  try {
    let s = String(ts).trim();
    if (!s.includes('T')) s = s.replace(' ', 'T');
    if (!s.endsWith('Z') && !s.includes('+')) s = s + 'Z';
    const d = new Date(s);
    const opts = short
      ? { hour: '2-digit', minute: '2-digit', second: '2-digit' }
      : { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', second: '2-digit' };
    return new Intl.DateTimeFormat('id-ID', { timeZone: 'Asia/Jakarta', ...opts }).format(d) + ' WIB';
  } catch (e) {
    return ts;
  }
}

async function updateChart() {
  const response = await fetch('/api/sensor/latest');
  const data = await response.json();
  const time = data.timestamp ? formatToWIB(data.timestamp, true) : formatToWIB(new Date().toISOString(), true);

  // Tambahkan data baru
  chartData.labels.push(time);
  chartData.datasets[0].data.push(data.temperature);
  chartData.datasets[1].data.push(data.humidity);
  chartData.datasets[2].data.push(data.water_level_cm);
  chartData.datasets[3].data.push(data.ph_value ?? null);

  // Batasi jumlah data (misal 10)
  if (chartData.labels.length > 10) {
    chartData.labels.shift();
    chartData.datasets[0].data.shift();
    chartData.datasets[1].data.shift();
    chartData.datasets[2].data.shift();
    chartData.datasets[3].data.shift();
  }

  sensorChart.update();
}

// Update chart setiap 3 detik
setInterval(updateChart, 3000);
updateChart();