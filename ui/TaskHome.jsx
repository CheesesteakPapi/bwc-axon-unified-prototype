export function TaskHome({ tasks, children, description = "Prepare accounts, check equipment, or review location matches." }) {
  return <section className="task-home" aria-labelledby="task-home-title">
    <h1 id="task-home-title">What would you like to do?</h1><p className="task-intro">{description}</p>
    <div className="task-home-layout"><div className="task-rows">{tasks.map(({ title, description: detail, action, onClick, primary }) =>
      <article className="task-row" key={title}><div><h2>{title}</h2><p>{detail}</p></div>
        <button type="button" className={primary ? "task-primary" : "task-link"} onClick={onClick}>{action}</button>
      </article>)}</div><aside className="task-context">{children}</aside></div>
  </section>;
}

export function TaskNavigation({ items, current, onNavigate, help }) {
  return <header className="task-nav"><strong>BWC Operations</strong><nav aria-label="Main tasks">{items.map(([key, label]) =>
    <button key={key} type="button" aria-current={current === key ? "page" : undefined} onClick={() => onNavigate(key)}>{label}</button>
  )}</nav><button type="button" className="task-help" onClick={help}>Help</button></header>;
}
