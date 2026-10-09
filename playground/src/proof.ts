const worker = new Worker(new URL('./proof.worker.ts', import.meta.url), { type: 'module' });
worker.onmessage = event => {
  if (event.data.phase) {
    document.body.querySelector('p')!.textContent = event.data.phase;
    return;
  }
  if (event.data.error) {
    document.body.textContent = event.data.error;
    document.body.dataset.complete = 'error';
    worker.terminate();
    return;
  }
  for (const result of event.data.results) {
    const link = document.createElement('a');
    link.textContent = result.name;
    link.download = `${result.name}.browser.pdf`;
    link.href = URL.createObjectURL(new Blob([result.pdf], { type: 'application/pdf' }));
    document.body.append(link, document.createElement('br'));
  }
  document.body.dataset.complete = 'true';
  worker.terminate();
};
worker.onerror = event => {
  document.body.textContent = event.message;
  document.body.dataset.complete = 'error';
  worker.terminate();
};
