document.getElementById('changeText').addEventListener('click', function() {
    const greetingElement = document.getElementById('greeting');
    const newText = greetingElement.textContent === 'Hello, World!' ? '你好，世界！' : 'Hello, World!';
    greetingElement.textContent = newText;
});