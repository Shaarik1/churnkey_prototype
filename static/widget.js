(function() {
    console.log("RetainAI Widget Loaded");

    let config = {
        color: '#2563EB',
        projectId: 'demo_client_1' // Default if they forget to set one
    };

    const container = document.createElement('div');
    container.id = 'retain-ai-container';
    container.style.position = 'fixed';
    container.style.top = '0';
    container.style.left = '0';
    container.style.width = '100vw';
    container.style.height = '100vh';
    container.style.zIndex = '999999';
    container.style.display = 'none';
    container.style.backgroundColor = 'transparent'; 

    const iframe = document.createElement('iframe');
    iframe.style.width = '100%';
    iframe.style.height = '100%';
    iframe.style.border = 'none';
    iframe.allowTransparency = "true"; 

    container.appendChild(iframe);
    document.body.appendChild(container);

    window.RetainAI = {
        init: function(userConfig) {
            if (userConfig) {
                config = { ...config, ...userConfig };
            }
            // FIX: We now pass BOTH color AND project_id to the iframe
            const iframeUrl = `https://churnkey-demo.onrender.com/demo?color=${encodeURIComponent(config.color)}&project_id=${encodeURIComponent(config.projectId)}`;
            iframe.src = iframeUrl;
        },
        open: function() {
            container.style.display = 'block';
        },
        close: function() {
            container.style.display = 'none';
            iframe.src = iframe.src; // Reset state
        }
    };

    window.RetainAI.init(); // Run defaults

    window.addEventListener('message', function(event) {
        if (event.data === 'close-modal') {
            window.RetainAI.close();
        }
    });
})();