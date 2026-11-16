type ReasonPillProps = {
    children: string
}

export default function ReasonPill({children}: ReasonPillProps){
    return <span className="reason-pill">{children}</span>
}