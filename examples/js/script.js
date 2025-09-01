fetch('examples/devices_with_scores.json')
    .then(response => response.json())
    .then(data => {
        const list = document.getElementById('device-list');
        data.forEach(device => {
            const li = document.createElement('li');
            li.textContent = `${device.name} (${device.brand || 'Unknown Brand'}): ${device.repairability_score}`;
            list.appendChild(li);
        });
    })
    .catch(error => console.error('Error loading JSON data:', error));