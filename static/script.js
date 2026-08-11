async function fetchBotStats() {
  try {
    const response = await fetch('/api/stats');
    if (!response.ok) throw new Error('API unreachable');
    
    const data = await response.json();
    
    document.getElementById('botStatus').textContent = data.status;
    document.getElementById('serverCount').textContent = data.guild_count;
    document.getElementById('botPing').textContent = `${data.latency} ms`;
  } catch (error) {
    document.getElementById('botStatus').textContent = 'Offline';
    document.getElementById('botStatus').style.color = '#ef4444';
  }
}

// Fetch stats immediately, then refresh every 10 seconds
fetchBotStats();
setInterval(fetchBotStats, 10000);
