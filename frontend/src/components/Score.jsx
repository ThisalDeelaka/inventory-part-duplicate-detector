export default function Score({value}) { return <div className="score"><b>{value.toFixed(1)}</b><div><span style={{width:`${value}%`}} /></div></div> }
