import { Component, type ErrorInfo, type ReactNode } from "react"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"

type Props = { children: ReactNode }
type State = { error: Error | null }

/** Top-level boundary: catches render errors and offers a clean relaunch. */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("Unhandled UI error", error, info)
  }

  render() {
    if (this.state.error) {
      return (
        <div className="flex min-h-svh items-center justify-center p-6">
          <div className="w-full max-w-md space-y-4">
            <Alert variant="destructive">
              <AlertTitle>Something went wrong</AlertTitle>
              <AlertDescription>
                {this.state.error.message || "The interface hit an unexpected error."}
              </AlertDescription>
            </Alert>
            <Button
              onClick={() => {
                this.setState({ error: null })
                window.location.reload()
              }}
            >
              Reload
            </Button>
          </div>
        </div>
      )
    }
    return this.props.children
  }
}
