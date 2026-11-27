function drawProjectChart(target, points) {
    const matrix = named('div',undefined,'charging-matrix');
    const scale = Math.max(...points.map(entry=>Math.abs(entry.value)),1);
    for (const point of points) {
        const cell = named('div',undefined,'charging-cell');
        cell.style.setProperty('--charge',`${Math.abs(point.value)/scale*78}%`);
        cell.append(named('span',point.label),named('strong',point.value));
        matrix.append(cell);
    }
    target.append(matrix);
}
