// Global Vanta Initialization
document.addEventListener('DOMContentLoaded', () => {
    if (window.VANTA && document.getElementById('vanta-bg')) {
        VANTA.GLOBE({
            el: "#vanta-bg",
            mouseControls: true,
            touchControls: true,
            gyroControls: false,
            minHeight: 200.00,
            minWidth: 200.00,
            scale: 1.00,
            scaleMobile: 1.00,
            color: 0x5773ff,
            backgroundColor: 0x0a0a12,
            size: 0.8
        });
    }
});

// React will call this when Hero section mounts
window.initThreeJS = function() {
    if (typeof THREE === 'undefined') return;
    
    // Torus
    const torusCanvas = document.getElementById('torusCanvas');
    if (torusCanvas && !torusCanvas.initialized) {
        torusCanvas.initialized = true;
        const torusScene = new THREE.Scene();
        const torusCamera = new THREE.PerspectiveCamera(75, 1, 0.1, 1000);
        const torusRenderer = new THREE.WebGLRenderer({ canvas: torusCanvas, alpha: true, antialias: true });
        const torusGeometry = new THREE.TorusGeometry(1, 0.4, 16, 100);
        const torusMaterial = new THREE.MeshBasicMaterial({ color: 0x5773ff, wireframe: true, transparent: true, opacity: 0.8 });
        const torus = new THREE.Mesh(torusGeometry, torusMaterial);
        torusScene.add(torus);
        torusCamera.position.z = 3;
        
        function animateTorus() {
            requestAnimationFrame(animateTorus);
            torus.rotation.x += 0.01;
            torus.rotation.y += 0.005;
            torusRenderer.render(torusScene, torusCamera);
        }
        animateTorus();
    }
    
    // Cube
    const cubeCanvas = document.getElementById('cubeCanvas');
    if (cubeCanvas && !cubeCanvas.initialized) {
        cubeCanvas.initialized = true;
        const cubeScene = new THREE.Scene();
        const cubeCamera = new THREE.PerspectiveCamera(75, 1, 0.1, 1000);
        const cubeRenderer = new THREE.WebGLRenderer({ canvas: cubeCanvas, alpha: true, antialias: true });
        const cubeGeometry = new THREE.BoxGeometry(1, 1, 1);
        const cubeMaterial = new THREE.MeshBasicMaterial({ color: 0xff007a, wireframe: true, transparent: true, opacity: 0.6 });
        const cube = new THREE.Mesh(cubeGeometry, cubeMaterial);
        cubeScene.add(cube);
        cubeCamera.position.z = 3;
        
        function animateCube() {
            requestAnimationFrame(animateCube);
            cube.rotation.x += 0.01;
            cube.rotation.y += 0.01;
            cubeRenderer.render(cubeScene, cubeCamera);
        }
        animateCube();
    }
    
    // Pyramid
    const pyramidCanvas = document.getElementById('pyramidCanvas');
    if (pyramidCanvas && !pyramidCanvas.initialized) {
        pyramidCanvas.initialized = true;
        const pyramidScene = new THREE.Scene();
        const pyramidCamera = new THREE.PerspectiveCamera(75, 1, 0.1, 1000);
        const pyramidRenderer = new THREE.WebGLRenderer({ canvas: pyramidCanvas, alpha: true, antialias: true });
        const pyramidGeometry = new THREE.ConeGeometry(0.8, 1.5, 4);
        const pyramidMaterial = new THREE.MeshBasicMaterial({ color: 0x00f0ff, wireframe: true, transparent: true, opacity: 0.6 });
        const pyramid = new THREE.Mesh(pyramidGeometry, pyramidMaterial);
        pyramid.rotation.y = Math.PI / 4;
        pyramidScene.add(pyramid);
        pyramidCamera.position.z = 3;
        
        function animatePyramid() {
            requestAnimationFrame(animatePyramid);
            pyramid.rotation.x -= 0.01;
            pyramid.rotation.y -= 0.01;
            pyramidRenderer.render(pyramidScene, pyramidCamera);
        }
        animatePyramid();
    }
};